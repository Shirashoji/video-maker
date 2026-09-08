import json
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

from video_maker.engine import prepare, render
from video_maker.graphics import font_path
from video_maker.media import ffmpeg
from video_maker.models import Graphic, Project
from video_maker.motion import artwork, frame_at, state_at


@pytest.mark.parametrize('change', [
    {'kind': 'text'}, {'kind': 'arrow'}, {'fill': 'red'}, {'end': 0.5, 'start': 1},
    {'keyframes': [{'time': 1, 'x': 0, 'y': 0}, {'time': 0, 'x': 0, 'y': 0}]},
    {'opacity': float('nan')}, {'keyframes': [{'time': 3, 'x': 0, 'y': 0}], 'end': 2},
])
def test_invalid_graphics(change):
    with pytest.raises(ValidationError):
        Graphic.model_validate({'kind': 'rect', **change})


def test_interpolation_and_visibility():
    g = Graphic(kind='rect', start=1, end=4, keyframes=[
        {'time': 0, 'x': 0, 'y': 0, 'opacity': 0, 'easing': 'linear'},
        {'time': 2, 'x': 0.8, 'y': 0.4, 'scale': 2}])
    assert state_at(g, 0.9, 5) is None
    assert state_at(g, 2, 5) == (0.4, 0.2, 1.5, 0.5)
    assert state_at(g, 3.9, 5) == (0.8, 0.4, 2, 1)
    assert state_at(g, 4, 5) is None
    g.enter = 'pop'
    assert state_at(g, 1, 5)[3] == 0


@pytest.mark.parametrize('effect', ['fade', 'slide_left', 'slide_up', 'pop'])
def test_short_entrance_and_exit(effect):
    g = Graphic(kind='rect', start=1, end=1.2, enter=effect, exit=effect)
    assert state_at(g, 1, 2)[3] == 0
    assert state_at(g, 1.1, 2)[3] == pytest.approx(1)
    assert state_at(g, 1.199, 2)[3] < 0.04
    assert state_at(g, 1.2, 2) is None


def test_published_schema_and_example_match_models():
    assert json.loads(Path('docs/project.schema.json').read_text()) == Project.model_json_schema()
    Project.model_validate_json(Path('examples/motion-graphics.json').read_text())


def test_artwork_shapes_text_and_layer_order():
    font = font_path()
    graphics = [Graphic(kind='rect', x=0, y=0, width=1, height=1, fill='#FF0000'),
                Graphic(kind='ellipse', x=0.2, y=0.2, width=0.6, height=0.6, fill='#00FF00')]
    im = frame_at([(g, artwork(g, 320, 240, font)) for g in graphics], 0.5, 1, 320, 240)
    assert im.getpixel((160,120)) == (0,255,0,255)
    assert im.getpixel((0,0))[3] == 0  # rounded corner
    for kind in ('arrow', 'line'):
        g = Graphic(kind=kind, x=0.8, y=0.8, x2=0.1, y2=0.1)
        assert artwork(g,320,240,font)[0].getbbox()
    for style in ('plain', 'impact', 'banner'):
        g = Graphic(kind='text', text='図解と強調\n日本語テロップ', style=style, height=0.4)
        assert artwork(g,320,240,font)[0].getbbox()


def test_graphic_bounds_with_resolved_duration(tmp_path):
    p = Project(name='Bounds', scenes=[{'id':'a','duration':1,'graphics':[
        {'kind':'rect','keyframes':[{'time':2,'x':0,'y':0}]}]}])
    with pytest.raises(ValueError, match='past scene end'):
        prepare(tmp_path,p,tmp_path)


def test_render_motion_over_video_and_slide(tmp_path):
    ffmpeg(['-f','lavfi','-i','color=blue:s=320x240:r=30:d=2',
            '-c:v','libx264',str(tmp_path/'input.mp4')])
    p = Project(name='Motion', width=1280, height=960, scenes=[{
        'id':'video', 'source':'input.mp4', 'source_rect':[0.5,0.5,0.5,0.5],
        'background':'#000000','duration':2, 'graphics':[
            {'kind':'rect','x':0.1,'y':0.1,'width':0.2,'height':0.2,
             'radius':0,'fill':'#FF0000','start':0.2,'end':1.8,
             'keyframes':[{'time':0,'x':0.1,'y':0.1,'easing':'linear'},
                          {'time':1,'x':0.5,'y':0.1}]},
            {'kind':'text','text':'注目！','style':'impact','y':0.8,'height':0.15,'enter':'pop'}],
        'captions':[{'text':'字幕はSRTにも出力','start':0.1,'end':0.8}]},
        {'id':'slide','duration':1,'background':'#004400','transition':'fade',
         'graphics':[{'kind':'text','text':'説明スライド','style':'banner','enter':'slide_up'}]}])
    (tmp_path/'p.json').write_text(p.model_dump_json())
    result = render(tmp_path,'p.json',preview=True)
    assert abs(result['duration'] - 2.6) < 0.1
    assert '注目' not in Path(result['captions']).read_text()
    assert '字幕は' in Path(result['captions']).read_text()
    for t, pos, expected in [(0,(100,80),(0,0,0)), (0.3,(125,80),(255,0,0)),
                             (1.3,(360,80),(255,0,0)), (1.3,(100,80),(0,0,0)),
                             (1.3,(550,300),(0,0,255))]:
        path=tmp_path/f'frame-{t}-{pos[0]}.png'
        ffmpeg(['-ss',str(t),'-i',result['video'],'-frames:v','1',str(path)])
        with Image.open(path) as im:
            assert all(abs(a-b)<15 for a,b in zip(im.getpixel(pos),expected))
