import json
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "workspace/projects/chofu-detailed-2024-voice.json"
DEST = ROOT / "workspace/projects/chofu-demo-2024-voice.json"


def replace_text(scene, old, new):
    for graphic in scene.get("graphics", []):
        if graphic.get("kind") == "text" and graphic.get("text") == old:
            graphic["text"] = new


base = json.loads(SOURCE.read_text())
by_id = {scene["id"]: scene for scene in base["scenes"]}
selected = ["hero", "overview", "explore", "numbers", "years", "filter", "closing"]

project = {
    "name": "Chofu Population Vis — 2024年対応 60秒デモ",
    "width": 1920,
    "height": 1080,
    "fps": 30,
    "transition_seconds": 0.4,
    "credits": deepcopy(base["credits"]),
    "readings": deepcopy(base["readings"]),
    "scenes": [deepcopy(by_id[scene_id]) for scene_id in selected],
}

for scene in project["scenes"]:
    scene.pop("duration", None)
    scene["caption_mode"] = "burn"
    scene["voice"]["speed"] = 1.11

hero = project["scenes"][0]
hero["voice"]["text"] = (
    "Chofu Population Vis。\n"
    "調布市の町丁別人口を。\n"
    "2017年から2024年まで。\n"
    "地図とチャートで探索するアプリです。"
)

overview = project["scenes"][1]
overview["voice"]["text"] = (
    "2024年の画面です。\n"
    "左の地図に地域特徴度。\n"
    "右に男女別・年齢別の人口を表示します。"
)
replace_text(overview, "01  2024年の人口を、ひとつの画面に。", "01  地図とチャートで、2024年を見る。")

explore = project["scenes"][2]
explore["speed"] = 1.1
explore["voice"]["text"] = (
    "地域にカーソルを重ねると。\n"
    "人口ピラミッドが切り替わります。\n"
    "クリックすれば、気になる地域を固定できます。"
)
replace_text(explore, "03  カーソルを重ねて、次々に比較。", "02  地域を動かして、比較する。")

numbers = project["scenes"][3]
numbers["voice"]["text"] = (
    "棒に触れると、人数と割合を確認できます。\n"
    "2024年の国領町3丁目では。\n"
    "45歳から49歳の男性が91人。\n"
    "割合は2.6217パーセントです。"
)
replace_text(numbers, "05  人数と割合を、セットで読む。", "03  人数と割合を、セットで読む。")

years = project["scenes"][4]
years["voice"]["text"] = (
    "Select Yearでは。\n"
    "2017年から2024年まで。\n"
    "8年分の変化を切り替えて見られます。"
)
replace_text(years, "07  2017–2024。8年分の変化を見る。", "04  2017–2024。8年分を切り替える。")

filter_scene = project["scenes"][5]
filter_scene["voice"]["text"] = (
    "Filterでは、Select YearとSelect Townから。\n"
    "年と地域を直接選べます。\n"
    "大きなチャートで、年代ごとの特徴を確認できます。"
)
replace_text(filter_scene, "08  Filterで、町名から直接選ぶ。", "05  Filterで、地域へ直接移動。")

closing = project["scenes"][6]
closing["voice"]["text"] = (
    "地図で気づき、チャートで確かめる。\n"
    "Chofu Population Vis。\n"
    "ブラウザで、地域を探索してみましょう。"
)
closing["duration"] = 7.733333333333333

DEST.write_text(json.dumps(project, ensure_ascii=False, indent=2) + "\n")
print(DEST)
