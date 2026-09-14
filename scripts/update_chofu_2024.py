import json
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "workspace/projects/chofu-detailed-v2.json"
VOICE_SOURCE = ROOT / "workspace/projects/chofu-detailed-voice.json"
DEST = ROOT / "workspace/projects/chofu-detailed-2024-voice.json"


def replace_text(scene, old, new):
    for graphic in scene.get("graphics", []):
        if graphic.get("kind") == "text" and graphic.get("text") == old:
            graphic["text"] = new


project = deepcopy(json.loads(SOURCE.read_text()))
voice_project = json.loads(VOICE_SOURCE.read_text())
voices = {scene["id"]: scene["voice"] for scene in voice_project["scenes"]}
project["name"] = "Chofu Population Vis — 2024年対応 詳細デモ"
project["credits"] = [
    "音声: VOICEVOX:四国めたん",
    "アプリケーション・提供素材: 白庄司 拓真",
    "説明資料: 学力向上アプリコンテスト応募ドキュメント",
]
project["readings"] = {
    "Chofu Population Vis": "チョウフポピュレーションビズ",
    "町丁別": "ちょうちょうべつ",
    "Select Year": "セレクトイヤー",
    "Select Town": "セレクトタウン",
    "Filter": "フィルター",
}

scenes = {scene["id"]: scene for scene in project["scenes"]}
for scene in project["scenes"]:
    scene["caption_mode"] = "burn"
    scene.pop("duration", None)
    scene["voice"] = deepcopy(voices[scene["id"]])
    scene.pop("audio", None)
    scene.pop("audio_text", None)
    scene.pop("captions", None)
    scene["graphics"] = [
        graphic
        for graphic in scene.get("graphics", [])
        if not (graphic.get("kind") == "text" and graphic.get("y") == 0.873)
    ]

# 00 — product introduction
hero = scenes["hero"]
hero["voice"]["text"] = (
    "Chofu Population Vis。\n"
    "街の違いを、人口のかたちから読み解く。\n"
    "2017年から2024年のデータを。\n"
    "地図とチャートで探索するアプリです。"
)
for graphic in hero["graphics"]:
    if graphic.get("kind") == "image":
        graphic["source"] = "assets/chofu-2024/map-unselected-clean.png"
replace_text(hero, "INTERACTIVE DEMO", "2024 DATA UPDATE")
for graphic in hero["graphics"]:
    if graphic.get("text") == "2024 DATA UPDATE":
        graphic["x"] = 0.58
        graphic["width"] = 0.35

# 01 — overview
overview = scenes["overview"]
overview["source"] = "assets/chofu-2024/map-unselected-clean.png"
overview["voice"]["text"] = (
    "調布市の町丁別人口を。\n"
    "地図と人口ピラミッドで表示します。\n"
    "左に地域、右に男女別・年齢別の人口。\n"
    "最新の2024年表示から、市内全域のかたちを見てみましょう。"
)
replace_text(overview, "01  地図と人口ピラミッドを、ひとつの画面に。", "01  2024年の人口を、ひとつの画面に。")

# 02 — regional feature
meaning = scenes["meaning"]
for graphic in meaning["graphics"]:
    if graphic.get("kind") == "image":
        graphic["source"] = "assets/chofu-2024/map-unselected-clean.png"

# 03 — hover exploration
explore = scenes["explore"]
explore["source"] = "assets/chofu-2024/recording-clean.mp4"
explore["source_in"] = 0
explore["speed"] = 0.9

# 04 — lock a town
lock = scenes["lock"]
lock["source"] = "assets/chofu-2024/recording-clean.mp4"
lock["source_in"] = 15.5
lock["speed"] = 0.78

# 05 — exact 2024 values
numbers = scenes["numbers"]
numbers["source"] = "assets/chofu-2024/tooltip-clean.png"
numbers["voice"]["text"] = (
    "棒にカーソルを重ねると。\n"
    "人数と地域内の割合が表示されます。\n"
    "2024年の国領町3丁目では。\n"
    "45歳から49歳の男性が91人。\n"
    "割合は、2.6217パーセントです。"
)
replace_text(numbers, "国領町3丁目  /  2021年表示", "国領町3丁目  /  2024年表示")
for graphic in numbers["graphics"]:
    if graphic.get("kind") == "image":
        graphic["source"] = "assets/chofu-2024/tooltip-detail.png"

# 06 — compare both sexes
age = scenes["age"]
age["voice"]["text"] = (
    "年齢のラベルにカーソルを重ねると。\n"
    "男女の数値を並べて確認できます。\n"
    "45歳から49歳では、男性91人、女性108人。\n"
    "人数と割合を、同じ年代で比較できます。"
)
for graphic in age["graphics"]:
    if graphic.get("kind") == "image":
        graphic["source"] = "assets/chofu-2024/age-detail.png"

# 07 — year range and reference date
years = scenes["years"]
years["source"] = "assets/chofu-2024/map-unselected-clean.png"
years.pop("source_in", None)
years.pop("speed", None)
years.pop("camera", None)
years["voice"]["text"] = (
    "Select Yearでは。\n"
    "2017年から2024年まで。\n"
    "8年分のデータを切り替えられます。\n"
    "2024年表示は、2025年1月1日時点の人口です。\n"
    "同じ地域を選び。\n"
    "地図の色とチャートの変化を追えます。"
)
replace_text(years, "07  年を切り替えて、同じ地域の変化を見る。", "07  2017–2024。8年分の変化を見る。")
replace_text(years, "年表示：元データのファイル年  /  基準日：翌年1月1日", "2024年表示  /  2025年1月1日時点")

# 08–09 — updated Filter screen
filter_scene = scenes["filter"]
filter_scene["source"] = "assets/chofu-2024/filter-2024.png"
filter_scene.pop("source_in", None)
filter_scene.pop("speed", None)
filter_scene.pop("camera", None)
filter_scene["voice"]["text"] = (
    "地名がわかっているときは、Filterへ。\n"
    "Select YearとSelect Townから。\n"
    "年と地域を直接選択します。\n"
    "2024年の目的の地域へ、すぐに移動できます。"
)

filter_detail = scenes["filter-detail"]
filter_detail["source"] = "assets/chofu-2024/filter-2024.png"
filter_detail.pop("source_in", None)
filter_detail.pop("speed", None)
filter_detail["camera"] = [
    {"time": 0, "zoom": 1, "x": 0.5, "y": 0.5, "easing": "ease_out"},
    {"time": 3.2, "zoom": 1.22, "x": 0.67, "y": 0.52},
]
filter_detail["voice"]["text"] = (
    "Filter画面では、人口ピラミッドを大きく表示します。\n"
    "この2024年の例では。\n"
    "20代の層が厚いことがひと目でわかります。\n"
    "棒や年齢ラベルに触れて、詳しい値も確認できます。"
)

# 10 — workflow stays conceptual, but make the year coverage visible.
workflow = scenes["workflow"]
workflow["voice"]["text"] = (
    "色から気になる地域を見つけ。\n"
    "人口ピラミッドのかたちを比べる。\n"
    "人数と割合で確かめ。\n"
    "年を切り替えて変化を追う。\n"
    "この往復が、地域を読み解く入口になります。"
)

# 11 — current public URL
closing = scenes["closing"]
closing["voice"]["text"] = (
    "身近な街の違いを、データから発見する。\n"
    "Chofu Population Vis。\n"
    "2017年から2024年の地域の姿を。\n"
    "ブラウザで探索してみましょう。"
)
replace_text(closing, "chofu-population-vis.netlify.app", "chofu-population-vis.shirashoji.com")

DEST.write_text(json.dumps(project, ensure_ascii=False, indent=2) + "\n")
print(DEST)
