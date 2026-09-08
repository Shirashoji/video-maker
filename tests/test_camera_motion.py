"""Track rendered landmarks across every frame: endpoints alone miss zoom jitter."""
import math

import pytest
from PIL import Image

from video_maker.media import ffmpeg
from video_maker.models import CameraKeyframe
from video_maker.motion import camera_filter


@pytest.mark.parametrize('fps', [24, 30, 60])
def test_subpixel_zoom_keeps_center_and_constant_velocity(tmp_path, fps):
    w, h = 320, 240
    image = Image.new('L', (w,h))
    image.putdata([round(230*(math.exp(-((x-80)**2+(y-120)**2)/32)
                            + math.exp(-((x-240)**2+(y-120)**2)/32)))
                   for y in range(h) for x in range(w)])
    source = tmp_path/'markers.png'
    image.save(source)
    # Hold before the first key and after the last key, and zoom linearly between them.
    keys = [CameraKeyframe(time=0.5, zoom=1, easing='linear'),
            CameraKeyframe(time=2.5, zoom=1.25)]
    output = tmp_path/'frames.gray'
    count = 3*fps+1
    ffmpeg(['-loop','1','-framerate',str(fps),'-i',str(source),
            '-vf',camera_filter(keys,fps,w,h)+'format=gray',
            '-frames:v',str(count),'-c:v','rawvideo','-f','rawvideo',str(output)])
    data = output.read_bytes()
    assert len(data) == count*w*h
    centers, positions, expected = [], [], []
    for frame in range(count):
        pixels = data[frame*w*h:(frame+1)*w*h]
        profile = [sum(pixels[x::w]) for x in range(w)]
        def centroid(a,b):
            return sum(x*profile[x] for x in range(a,b))/sum(profile[a:b])
        left, right = centroid(0,w//2), centroid(w//2,w)
        centers.append((left+right)/2)
        positions.append(left)
        zoom = 1+0.25*max(0,min(1,(frame/fps-0.5)/2))
        expected.append(160-80*zoom)
        # Both axes must use the same zoom and keep the selected focal point still.
        cy = sum(y*sum(pixels[y*w:(y+1)*w]) for y in range(h))/sum(pixels)
        assert abs(cy-120) < 0.05
    assert max(centers)-min(centers) < 0.05
    assert max(abs(a-b) for a,b in zip(positions,expected)) < 0.08
    assert max(abs((positions[i+1]-positions[i])-(expected[i+1]-expected[i]))
               for i in range(count-1)) < 0.08
