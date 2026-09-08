"""Editable starting points, not branded replicas or factual product claims."""
from typing import Literal

from .models import Project


def keynote_template(style: Literal['minimal', 'colorful'] = 'minimal', title: str = 'アイデアを、動かそう。',
                     subtitle: str = '映像と図解で、もっと伝わる。', source: str | None = None) -> dict:
    if style not in ('minimal', 'colorful'):
        raise ValueError('style must be minimal or colorful')
    dark = style == 'minimal'
    bg, ink = ('#090B10', '#F5F5F7') if dark else ('#F5F7FC', '#182235')
    accents = ['#69B8FF', '#AE8FFF', '#FF9DD8'] if dark else ['#4285F4', '#EA4335', '#34A853']
    panel = '#1A1F2D' if dark else '#FFFFFF'

    def text(value, x, y, w, h, **kw):
        return dict(kind='text', text=value, x=x, y=y, width=w, height=h,
                    fill=ink, stroke_width=0, font_size=0.055, **kw)

    intro = dict(id='hero', duration=4, background=bg, caption_mode='sidecar', graphics=[
        text('MAKE IT CLEAR', 0.1, 0.17, 0.8, 0.07, enter='fade'),
        {**text(title, 0.07, 0.30, 0.86, 0.28, enter='slide_up', animation_seconds=0.7),
         'font_size':0.13, 'gradient':{'colors':accents}},
        text(subtitle, 0.12, 0.66, 0.76, 0.09, start=0.8, enter='fade')])
    if not dark:
        intro['background_gradient'] = {'colors':['#F8FAFF','#E7EEFF','#FFF1E8'], 'direction':'diagonal'}
    cards = []
    for i, (heading, description) in enumerate([
        ('見せる', '録画で、実際の動きを。'), ('伝える', '図解で、仕組みを。'), ('印象に残す', '言葉と動きに、メリハリを。')]):
        x, start = 0.06+i*0.305, 0.25+i*0.22
        cards += [
            dict(kind='rect', x=x, y=0.30, width=0.27, height=0.43, fill=panel, radius=0.035,
                 shadow={'color':'#00000030', 'blur':0.025, 'y':0.014}, enter='slide_up', start=start,
                 animation_seconds=0.6),
            {**text(f'0{i+1}', x+0.025, 0.35, 0.22, 0.1, start=start+0.2, enter='fade', align='left'), 'fill':accents[i]},
            {**text(heading, x+0.025, 0.47, 0.22, 0.10, start=start+0.25, enter='fade', align='left'), 'font_size':0.06},
            {**text(description, x+0.025, 0.61, 0.22, 0.07, start=start+0.3, enter='fade', align='left'), 'font_size':0.027}]
    scenes = [intro, dict(id='features', duration=4.5, transition='fade', background=bg,
                         graphics=[text('一つの映像に、三つの表現。',0.08,0.08,0.84,0.13), *cards])]
    if source:
        scenes.append(dict(id='demo', duration=5, source=source, source_rect=[0.08,0.20,0.84,0.70],
                           background=bg, transition='fade', caption_mode='sidecar',
                           camera=[{'time':0,'zoom':1},{'time':1,'zoom':1,'easing':'linear'},
                                   {'time':3,'zoom':1.25,'x':0.5,'y':0.5},{'time':4.8,'zoom':1.25}],
                           graphics=[text('実際の画面で、確かめる。',0.08,0.04,0.84,0.12, enter='fade')]))
    scenes.append(dict(id='closing', duration=3.5, transition='fade', background=bg, graphics=[
        {**text('伝わる体験を。',0.08,0.30,0.84,0.25,enter='slide_up',animation_seconds=0.7),
         'font_size':0.14,'gradient':{'colors':accents}},
        text('次のアイデアを、ここから。',0.15,0.65,0.7,0.10,start=0.6,enter='fade')]))
    return Project(name=f'Keynote / {style}', scenes=scenes).model_dump(mode='json', exclude_defaults=True)
