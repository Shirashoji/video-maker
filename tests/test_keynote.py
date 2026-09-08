import array
import math
import wave
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

from video_maker.engine import prepare, render, validate
from video_maker.graphics import font_path
from video_maker.media import ffmpeg
from video_maker.models import Gradient, Graphic, Project
from video_maker.motion import artwork, gradient_image, frame_at
from video_maker.templates import keynote_template


@pytest.mark.parametrize('style', ['minimal','colorful'])
def test_templates(style):
    p = Project.model_validate(keynote_template(style))
    assert len(p.scenes) == 3
    assert p.scenes[0].graphics[1].gradient
    with_source = Project.model_validate(keynote_template(style, source='assets/recording.mov'))
    assert with_source.scenes[2].camera[-1].zoom > 1
    assert Project.model_validate_json(Path(f'examples/keynote-{style}.json').read_text()) == p
    for scene in p.scenes:
        for g in scene.graphics:
            assert artwork(g,640,360,font_path())[0].getbbox()


@pytest.mark.parametrize('graphic', [
    {'kind':'image'}, {'kind':'rect','source':'x.png'},
    {'kind':'image','source':'x.png','gradient':{'colors':['#FFFFFF','#000000']}},
    {'kind':'rect','gradient':{'colors':['#FFFFFF']}},
])
def test_graphic_validation(graphic):
    with pytest.raises(ValidationError):
        Graphic.model_validate(graphic)


def test_gradient_alpha_and_direction():
    im=gradient_image(Gradient(colors=['#FF000000','#0000FFFF']), (256,256))
    assert im.getpixel((0,120)) == (255,0,0,0)
    assert im.getpixel((255,120)) == (0,0,255,255)
    im=gradient_image(Gradient(colors=['#FF0000','#00FF00','#0000FF'],direction='vertical'), (256,256))
    assert im.getpixel((50,127))[1] > 250
    assert im.getpixel((50,255)) == (0,0,255,255)


def test_image_fit_rounding_shadow_and_sandbox(tmp_path):
    Image.new('RGBA',(200,100),(255,0,0,128)).save(tmp_path/'image.png')
    font=font_path()
    g=Graphic(kind='image',source='image.png',x=0.25,y=0.25,width=0.5,height=0.5,
              radius=0.07, fit='cover', shadow={'blur':0.01,'y':0.03})
    im=frame_at([(g,artwork(g,320,240,font,tmp_path))],0.5,1,320,240)
    assert im.getpixel((160,120))[0]>100
    assert im.getpixel((160,190))[3]>0  # shadow outside the 180px bottom edge
    assert im.getpixel((20,20))[3]==0
    g.shadow=None
    g.fit='contain'
    im=frame_at([(g,artwork(g,320,240,font,tmp_path))],0.5,1,320,240)
    assert im.getpixel((160,61))[3]==0
    assert im.getpixel((160,120))[3]==128
    g.source='../escape.png'
    with pytest.raises(ValueError,match='inside workspace'):
        artwork(g,320,240,font,tmp_path)


def test_camera_and_effect_timing_validation(tmp_path):
    Image.new('RGB',(320,240),'red').save(tmp_path/'source.png')
    for scene in [
        {'id':'s','duration':1,'camera':[{'time':0}]},
        {'id':'s','duration':1,'source':'source.png','camera':[{'time':1},{'time':1}]},
        {'id':'s','duration':1,'sound_effects':[{'source':'a.wav','duration':0.05}]},
    ]:
        with pytest.raises(ValidationError):
            Project(name='bad',scenes=[scene])
    p=Project(name='bad',scenes=[{'id':'s','duration':1,'source':'source.png','camera':[{'time':2}]}])
    with pytest.raises(ValueError,match='camera extends'):
        prepare(tmp_path,p,tmp_path)


@pytest.mark.parametrize('video', [False, True])
def test_render_camera_effects_and_sidecar(tmp_path, video):
    im=Image.new('RGB',(320,240),'red')
    im.paste('blue',(160,0,320,240)); im.save(tmp_path/'source.png')
    ffmpeg(['-f','lavfi','-i','sine=frequency=800:duration=1','-c:a','pcm_s16le',str(tmp_path/'tone.wav')])
    if video:
        ffmpeg(['-loop','1','-i',str(tmp_path/'source.png'),'-t','0.8','-r','30','-c:v','libx264',
                '-pix_fmt','yuv420p',str(tmp_path/'source.mp4')])
    p=Project(name='Keynote test',width=320,height=240,scenes=[{
        'id':'s','duration':2,'source':'source.mp4' if video else 'source.png', 'speed':0.5 if video else 1,
        'camera':[{'time':0,'zoom':1},{'time':1,'zoom':2,'x':0.75,'easing':'hold'}],
        'sound_effects':[{'source':'tone.wav','start':0.5,'duration':0.4,'volume':0.8}],
        'caption_mode':'sidecar','captions':[{'text':'SRT only','start':0.1,'end':1}],
    }, {'id':'gradient','duration':1,'source':'source.png','source_rect':[0.5,0.5,0.5,0.5],
        'background_gradient':{'colors':['#00FF00','#00FF00']}, 'caption_mode':'off',
        'captions':[{'text':'Hidden','start':0.1,'end':0.9}],
        'graphics':[{'kind':'image','source':'source.png','x':0.6,'y':0.05,'width':0.3,'height':0.3,
                     'fit':'cover','shadow':{},'enter':'fade'}]}])
    (tmp_path/'p.json').write_text(p.model_dump_json())
    result=render(tmp_path,'p.json')
    assert abs(result['duration']-3)<0.1
    assert 'SRT only' in Path(result['captions']).read_text()
    assert 'Hidden' not in Path(result['captions']).read_text()
    assert not list(Path(result['video']).parent.glob('*-caption-*.png'))
    for t, color in [(0,0),(1.4,2)]:
        png=tmp_path/f'{t}.png'
        ffmpeg(['-ss',str(t),'-i',result['video'],'-frames:v','1',str(png)])
        with Image.open(png) as frame:
            pixel=frame.getpixel((20,120))
            assert pixel[color]>240
    png=tmp_path/'gradient.png'
    ffmpeg(['-ss','2.5','-i',result['video'],'-frames:v','1',str(png)])
    with Image.open(png) as frame:
        assert frame.getpixel((10,10))[1]>240
    wav=tmp_path/'mix.wav'
    ffmpeg(['-i',result['video'],'-vn','-ac','1','-c:a','pcm_s16le',str(wav)])
    with wave.open(str(wav)) as f:
        samples=array.array('h',f.readframes(f.getnframes()))
        rate=f.getframerate()
    def rms(a,b):
        values=samples[int(a*rate):int(b*rate)]
        return math.sqrt(sum(v*v for v in values)/len(values))
    assert rms(0.05,0.35)<5
    assert rms(0.6,0.7)>1000
    assert rms(1.1,1.5)<5
    with wave.open(str(Path(result['video']).parent/'s-stem.wav')) as f:
        assert not any(f.readframes(f.getnframes()))  # SFX never contaminates narration ducking stem
