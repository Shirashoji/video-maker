import asyncio
import json
import wave
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

from video_maker.engine import load, prepare, render
from video_maker.graphics import speech_windows
from video_maker.media import ffmpeg, inside, probe
from video_maker.models import Project
from video_maker.service import Service


def project(**kw):
    return Project(name="Test", width=320, height=240, fps=30, **kw)


def test_schema_rejects_bad_timeline():
    for scenes in [
        [{"id":"x","duration":2},{"id":"x","duration":3}],
        [{"id":"x","duration":2,"crop":[0.5,0,0.8,1]}],
        [{"id":"x","duration":2,"typo":1}],
        [{"id":"x","duration":2,"transition":"fade"}],
        [{"id":"x","duration":float('nan')}],
    ]:
        with pytest.raises(ValidationError): project(scenes=scenes)


def test_workspace_escape_and_symlink(tmp_path):
    with pytest.raises(ValueError): inside(tmp_path, "../outside", exists=False)
    (tmp_path/'escape').symlink_to('/tmp')
    with pytest.raises(ValueError): inside(tmp_path, "escape/x", exists=False)


def test_audio_not_silently_truncated(tmp_path):
    wav=tmp_path/'audio.wav'
    ffmpeg(['-f','lavfi','-i','sine=duration=2','-c:a','pcm_s16le',str(wav)])
    p=project(scenes=[{'id':'s','audio':'audio.wav','duration':1}])
    build=tmp_path/'build';build.mkdir()
    with pytest.raises(ValueError,match='too short'): prepare(tmp_path,p,build)


def test_render_cut_transition_and_timed_caption(tmp_path):
    p=project(scenes=[{'id':'a','duration':1.2,'background':'#cc0000',
                        'captions':[{'text':'日本語字幕','start':0.2,'end':0.9}]},
                       {'id':'b','duration':1.2,'background':'#0000cc','transition':'fade'},
                       {'id':'c','duration':0.8,'background':'#00cc00'}])
    (tmp_path/'project.json').write_text(p.model_dump_json())
    result=render(tmp_path,'project.json')
    assert abs(result['duration']-2.8)<0.1
    meta=probe(Path(result['video']))
    assert {s['codec_type'] for s in meta['streams']}=={'video','audio'}
    assert '日本語字幕' in Path(result['captions']).read_text()
    for t, channel in [(0.1,0),(1.5,2),(2.5,1)]:
        png=tmp_path/f'{t}.png'
        ffmpeg(['-ss',str(t),'-i',result['video'],'-frames:v','1',str(png)])
        pixel=Image.open(png).getpixel((5,5))
        assert pixel[channel]>150 and sum(pixel)-pixel[channel]<40


def test_revisions(tmp_path):
    s=Service(tmp_path)
    p=project(scenes=[{'id':'s','duration':1}]).model_dump()
    s.save('project.json',p)
    with pytest.raises(ValueError,match='exists'): s.save('project.json',p)
    p['name']='Updated'; s.save('project.json',p,True)
    assert len(list((tmp_path/'revisions').glob('*.json')))==1
    assert load(tmp_path,'project.json').name=='Updated'


def test_voicevox_contract_and_cache(tmp_path,monkeypatch):
    from video_maker.voicevox import Voicevox
    from video_maker.models import Voice
    import io
    b=io.BytesIO()
    with wave.open(b,'wb') as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(48000);f.writeframes(b'\0\0'*4800)
    calls=[]
    def request(self,endpoint,params=None,body=None,method='GET'):
        calls.append((endpoint,params,body,method))
        if endpoint=='/version': return b'"test"'
        if endpoint=='/audio_query': return b'{}'
        return b.getvalue()
    monkeypatch.setattr(Voicevox,'request',request)
    client=Voicevox();v=Voice(text='テスト',speaker=3,speed=1.2)
    path=client.synthesize(v,tmp_path)
    assert client.synthesize(v,tmp_path)==path
    assert sum(c[0]=='/synthesis' for c in calls)==1
    synth=next(c for c in calls if c[0]=='/synthesis')
    assert synth[2]['speedScale']==1.2 and synth[3]=='POST'


def test_mcp_stdio(tmp_path):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    import sys, os
    async def check():
        params=StdioServerParameters(command=sys.executable,args=['-m','video_maker.server','--workspace',str(tmp_path)],
                                    env={**os.environ,'PYTHONPATH':str(Path('src').resolve())})
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as client:
                await client.initialize()
                tools=await client.list_tools()
                assert {'save_project','render_final','psd_layers','presentation_template'} <= {t.name for t in tools.tools}
                template=await client.call_tool('presentation_template',{'style':'colorful'})
                assert not template.isError
                assert Project.model_validate_json(template.content[0].text).scenes[0].background_gradient
                schema=await client.call_tool('project_schema',{})
                assert 'Graphic' in json.loads(schema.content[0].text)['$defs']
                p=project(scenes=[{'id':'s','duration':1,'graphics':[
                    {'kind':'text','text':'テロップ','style':'impact','enter':'pop'}]}]).model_dump()
                saved=await client.call_tool('save_project',{'path':'p.json','project':p})
                assert not saved.isError
                bad=await client.call_tool('read_project',{'path':'../escape'})
                assert bad.isError
    asyncio.run(check())


def test_slow_source_audio_crop_and_music(tmp_path):
    source=tmp_path/'source.mp4'
    ffmpeg(['-f','lavfi','-i','testsrc2=size=320x240:rate=30:duration=1',
            '-f','lavfi','-i','sine=frequency=440:duration=1','-c:v','libx264','-c:a','aac','-shortest',str(source)])
    p=project(music={'source':'source.mp4','duck':True}, scenes=[
        {'id':'a','source':'source.mp4','source_in':0.1,'source_volume':0.2,'speed':0.25,
         'crop':[0.1,0.1,0.8,0.8],'duration':1.2},
        {'id':'b','duration':1.2,'transition':'slideright'},
        {'id':'c','duration':1.2,'transition':'wipeleft'}])
    (tmp_path/'p.json').write_text(p.model_dump_json())
    result=render(tmp_path,'p.json')
    assert abs(result['duration']-2.8)<0.1


def test_lip_sync_detects_speech_but_not_silence(tmp_path):
    wav=tmp_path/'n.wav'
    ffmpeg(['-f','lavfi','-i','sine=frequency=440:duration=0.4:sample_rate=48000',
            '-af','adelay=400,apad=pad_dur=0.4','-c:a','pcm_s16le',str(wav)])
    windows=speech_windows(wav,0.5)
    assert windows and windows[0][0]>=0.89 and windows[-1][1]<=1.31


def test_job_completes_and_survives_restart(tmp_path):
    import time
    s=Service(tmp_path)
    p=project(scenes=[{'id':'a','duration':0.8}])
    s.save('p.json',p.model_dump())
    job=s.start('p.json')['job_id']
    deadline=time.monotonic()+30
    while s.status(job)['status'] in ('queued','running') and time.monotonic()<deadline:
        time.sleep(0.05)
    assert s.status(job)['status']=='complete'
    assert Service(tmp_path).status(job)['status']=='complete'
