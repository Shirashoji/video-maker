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


def slide_template(variant: Literal['hero', 'features', 'comparison', 'stats'] = 'features',
                   title: str = 'メインタイトルをここに入力',
                   subtitle: str = '補足説明やサブタイトルをここに入力します。',
                   dark: bool = True) -> str:
    """Generate modern, 16:9 transparent-ready HTML slide markup."""
    bg_card = 'rgba(26, 31, 45, 0.85)' if dark else 'rgba(255, 255, 255, 0.92)'
    text_color = '#F5F5F7' if dark else '#182235'
    sub_color = '#94A3B8' if dark else '#64748B'
    border_color = 'rgba(255, 255, 255, 0.1)' if dark else 'rgba(0, 0, 0, 0.08)'

    css_base = f"""
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      width: 1920px;
      height: 1080px;
      overflow: hidden;
      background: transparent;
      font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans", "Noto Sans JP", sans-serif;
      color: {text_color};
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: center;
      padding: 80px 100px;
    }}
    .gradient-text {{
      background: linear-gradient(135deg, #38BDF8, #818CF8 50%, #F472B6);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }}
    .card {{
      background: {bg_card};
      border: 1px solid {border_color};
      border-radius: 24px;
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.35);
      backdrop-filter: blur(16px);
    }}
    """

    if variant == 'hero':
        content = f"""
        <div class="card" style="padding: 64px 80px; text-align: center; max-width: 1400px; width: 100%;">
          <div style="display: inline-block; padding: 8px 24px; border-radius: 9999px; background: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.4); color: #38BDF8; font-weight: 600; font-size: 24px; margin-bottom: 32px; letter-spacing: 0.05em;">KEY POINT</div>
          <h1 class="gradient-text" style="font-size: 76px; font-weight: 800; line-height: 1.25; margin-bottom: 28px;">{title}</h1>
          <p style="font-size: 34px; color: {sub_color}; line-height: 1.6; max-width: 1000px; margin: 0 auto;">{subtitle}</p>
        </div>
        """
    elif variant == 'comparison':
        content = f"""
        <div style="width: 100%; max-width: 1600px;">
          <h2 style="font-size: 52px; font-weight: 800; text-align: center; margin-bottom: 50px;">{title}</h2>
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 48px;">
            <div class="card" style="padding: 48px; border-left: 6px solid #EF4444;">
              <div style="font-size: 24px; font-weight: bold; color: #EF4444; margin-bottom: 16px;">これまで (Before)</div>
              <h3 style="font-size: 36px; margin-bottom: 20px;">手作業の座標計算</h3>
              <p style="font-size: 26px; color: {sub_color}; line-height: 1.6;">位置や文字幅の見積もりが難しく、ズレや重なりが発生しやすい。</p>
            </div>
            <div class="card" style="padding: 48px; border-left: 6px solid #10B981;">
              <div style="font-size: 24px; font-weight: bold; color: #10B981; margin-bottom: 16px;">これから (After)</div>
              <h3 style="font-size: 36px; margin-bottom: 20px;">HTML & Mermaid 連携</h3>
              <p style="font-size: 26px; color: {sub_color}; line-height: 1.6;">Web標準のFlexboxや自動ダイアグラムで、AIが直感的にレイアウト。</p>
            </div>
          </div>
        </div>
        """
    elif variant == 'stats':
        content = f"""
        <div style="width: 100%; max-width: 1600px; text-align: center;">
          <h2 style="font-size: 52px; font-weight: 800; margin-bottom: 60px;">{title}</h2>
          <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 40px;">
            <div class="card" style="padding: 48px 32px;">
              <div class="gradient-text" style="font-size: 72px; font-weight: 800; margin-bottom: 12px;">3x</div>
              <div style="font-size: 24px; font-weight: 600; color: {sub_color};">制作スピード向上</div>
            </div>
            <div class="card" style="padding: 48px 32px;">
              <div class="gradient-text" style="font-size: 72px; font-weight: 800; margin-bottom: 12px;">0</div>
              <div style="font-size: 24px; font-weight: 600; color: {sub_color};">手動座標計算の工数</div>
            </div>
            <div class="card" style="padding: 48px 32px;">
              <div class="gradient-text" style="font-size: 72px; font-weight: 800; margin-bottom: 12px;">100%</div>
              <div style="font-size: 24px; font-weight: 600; color: {sub_color};">Web標準の表現力</div>
            </div>
          </div>
        </div>
        """
    else:  # features
        content = f"""
        <div style="width: 100%; max-width: 1600px;">
          <h2 style="font-size: 52px; font-weight: 800; text-align: center; margin-bottom: 16px;">{title}</h2>
          <p style="font-size: 28px; color: {sub_color}; text-align: center; margin-bottom: 60px;">{subtitle}</p>
          <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 40px;">
            <div class="card" style="padding: 44px 36px;">
              <div style="font-size: 32px; font-weight: 700; color: #38BDF8; margin-bottom: 16px;">01. Flexbox</div>
              <p style="font-size: 24px; color: {sub_color}; line-height: 1.6;">自動折り返しと均等配置で崩れない美しいUIカード。</p>
            </div>
            <div class="card" style="padding: 44px 36px;">
              <div style="font-size: 32px; font-weight: 700; color: #818CF8; margin-bottom: 16px;">02. Mermaid</div>
              <p style="font-size: 24px; color: {sub_color}; line-height: 1.6;">テキストで関係性を定義するだけの自動ダイアグラム。</p>
            </div>
            <div class="card" style="padding: 44px 36px;">
              <div style="font-size: 32px; font-weight: 700; color: #F472B6; margin-bottom: 16px;">03. Animation</div>
              <p style="font-size: 24px; color: {sub_color}; line-height: 1.6;">透過動画合成でフェード・スライド・ポップを自在に付与。</p>
            </div>
          </div>
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <style>{css_base}</style>
</head>
<body>
{content}
</body>
</html>"""


def mermaid_template(variant: Literal['flowchart', 'sequence', 'architecture'] = 'flowchart') -> str:
    """Generate modern, readable Mermaid diagram templates."""
    if variant == 'sequence':
        return """sequenceDiagram
    autonumber
    actor User as ユーザー
    participant Agent as 生成AI Agent
    participant Engine as Video Maker
    participant FFmpeg as FFmpeg / VOICEVOX

    User->>Agent: 動画作成リクエスト
    Agent->>Agent: HTMLスライド & Mermaid図解作成
    Agent->>Engine: project.json 保存 & タイムライン計画
    Engine->>FFmpeg: 音声合成 & 透過動画レンダリング
    FFmpeg-->>Engine: MP4動画生成完了
    Engine-->>Agent: ジョブ完了ステータス
    Agent-->>User: 完成動画をプレビュー報告
"""
    elif variant == 'architecture':
        return """graph LR
    subgraph Input [入力データ]
        M[Mermaid .mmd]
        H[HTML/CSS スライド]
        S[音声 & 録画素材]
    end

    subgraph Renderer [Web / Vector レンダラー]
        MC[Mermaid CLI]
        CH[Headless Chrome]
        RS[resvg-py]
    end

    subgraph Engine [Video Maker コア]
        MO[motion.py<br/>キーフレーム・イージング]
        FF[FFmpeg<br/>レイヤー透過合成]
    end

    M --> MC
    H --> CH
    Input --> RS
    MC --> MO
    CH --> MO
    RS --> MO
    S --> FF
    MO --> FF
    FF --> Out[完成 MP4]

    style Input fill:#1e293b,stroke:#475569,stroke-width:2px,color:#fff
    style Renderer fill:#0f172a,stroke:#38bdf8,stroke-width:2px,color:#fff
    style Engine fill:#1e1b4b,stroke:#818cf8,stroke-width:2px,color:#fff
    style Out fill:#064e3b,stroke:#10b981,stroke-width:2px,color:#fff
"""
    else:  # flowchart
        return """graph TD
    A[リクエスト受領] --> B{図解の種類}
    B -->|プロセス・手順| C[フローチャート (Mermaid)]
    B -->|リッチスライド| D[HTML/CSS (Flexbox)]
    B -->|アイコン・ロゴ| E[ベクター画像 (SVG)]

    C --> F[透過PNG/SVG生成]
    D --> F
    E --> F

    F --> G[Video Maker<br/>タイムライン合成 & アニメーション]
    G --> H[完成 MP4]

    style A fill:#38bdf8,stroke:#0284c7,stroke-width:2px,color:#fff
    style B fill:#818cf8,stroke:#4f46e5,stroke-width:2px,color:#fff
    style C fill:#34d399,stroke:#059669,stroke-width:2px,color:#fff
    style D fill:#f472b6,stroke:#db2777,stroke-width:2px,color:#fff
    style E fill:#fbbf24,stroke:#d97706,stroke-width:2px,color:#fff
    style G fill:#6366f1,stroke:#4338ca,stroke-width:2px,color:#fff
    style H fill:#10b981,stroke:#047857,stroke-width:2px,color:#fff
"""

