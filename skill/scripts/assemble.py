"""Lay stems on the song timeline. Song t=0 = backing bar 4 at 140 BPM. Each source: (file, offset_s) summed into one stem.
Usage: assemble.py out.wav length_s file@offset [file@offset ...]
"""
import sys
import numpy as np, soundfile as sf

SR = 44100
out, length = sys.argv[1], float(sys.argv[2])
acc = np.zeros((int(length * SR), 2))
for spec in sys.argv[3:]:
    path, off = spec.rsplit("@", 1)
    x, sr = sf.read(path, always_2d=True)
    assert sr == SR
    if x.shape[1] == 1:
        x = np.repeat(x, 2, axis=1)
    i = int(round(float(off) * SR))
    n = min(len(x), len(acc) - i)
    acc[i:i + n] += x[:n]
sf.write(out, acc, SR, subtype="PCM_24")
print(f"{out}: {len(sys.argv) - 3} sources, peak {np.abs(acc).max():.2f}")
