"""Create an editable keynote demo and an original, quiet transition cue."""
import argparse
import array
import json
import math
import random
import sys
import uuid
import wave
from pathlib import Path

from video_maker.models import Project
from video_maker.templates import keynote_template


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', type=Path, default=Path('workspace'))
    parser.add_argument('--style', choices=['minimal','colorful'], default='minimal')
    parser.add_argument('--source', help='Existing workspace-relative recording; inspect footage before selecting')
    args = parser.parse_args()
    root = args.workspace.resolve()
    folder = root / 'assets' / 'keynote-demo' / uuid.uuid4().hex
    folder.mkdir(parents=True)
    cue = folder / 'air.wav'
    rng, samples, previous = random.Random(42), array.array('h'), 0.0
    rate, seconds = 48000, 0.5
    for i in range(round(rate*seconds)):
        t = i/rate
        previous = 0.94*previous + 0.06*rng.uniform(-1,1)
        envelope = math.sin(math.pi*t/seconds)**2
        samples.append(round(11000*previous*envelope))
    if sys.byteorder != 'little':
        samples.byteswap()
    with wave.open(str(cue),'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(rate); f.writeframes(samples.tobytes())
    p = keynote_template(args.style, '複雑を、シンプルに。', '録画・図解・言葉が、一つのストーリーに。', args.source)
    for scene in p['scenes']:
        scene['sound_effects'] = [{'source':str(cue.relative_to(root)), 'start':0.12,
                                   'duration':seconds, 'volume':0.25}]
    p['credits'] = ['Transition cue: original deterministic filtered noise, scripts/create_keynote_demo.py']
    path = root / f'keynote-{args.style}-{folder.name[:8]}.json'
    path.write_text(Project.model_validate(p).model_dump_json(indent=2), encoding='utf-8')
    print(json.dumps({'project':str(path), 'relative_project':str(path.relative_to(root))}, ensure_ascii=False))


if __name__ == '__main__':
    main()
