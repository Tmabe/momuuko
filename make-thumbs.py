# -*- coding: utf-8 -*-
"""
포트폴리오 이미지 경량화
  portfolio/*.png  ->  portfolio/thumb/*.webp   가로  400px (그리드 썸네일)
                   ->  portfolio/view/*.webp    가로 1400px (뷰어 패널 감상용)

artmug.html 은 썸네일 -> 감상용 -> 원본 순으로 폴백한다(onerror).
그래서 새 그림을 올린 뒤 이 스크립트를 안 돌려도 페이지는 정상 동작하고,
돌리면 그만큼 가벼워진다. 원본은 그대로 두므로 언제든 되돌릴 수 있다.

사용법:
    python make-thumbs.py            # 새로 생기거나 원본이 바뀐 것만 처리
    python make-thumbs.py --force    # 전부 다시 생성
    python make-thumbs.py --faces    # portfolio/face/ 얼굴만 잘린 정사각 썸네일도 생성
                                     # (지금 페이지는 안 쓰지만 좌표는 faces.json 에 남겨둠)
"""
import sys, os
from PIL import Image

SRC   = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'portfolio')
SIZES = [('thumb', 400, 82), ('view', 1400, 86)]   # (폴더, 가로px, 품질)
FACE  = ('face', 320, 84)                          # 얼굴만 잘라낸 정사각 썸네일
EXTS  = ('.png', '.jpg', '.jpeg', '.gif', '.webp')


def load_faces():
    """portfolio/faces.json = 얼굴 위치(비율). 없으면 기본 규칙만 쓴다."""
    path = os.path.join(SRC, 'faces.json')
    if not os.path.exists(path):
        return {}, {'세로형': {'x': .469, 'y': .085, 's': .52},
                    '가로형': {'x': .230, 'y': .070, 's': .130}}
    import json
    with open(path, encoding='utf-8') as f:
        d = json.load(f)
    defaults = d.get('_기본값', {})
    boxes = {k: v for k, v in d.items() if not k.startswith('_')}
    return boxes, defaults


def crop_face(im, name, boxes, defaults):
    """얼굴 정사각 영역을 잘라 반환. 지정값 없으면 판형별 기본 규칙."""
    w, h = im.size
    box = boxes.get(name) or defaults.get('세로형' if h >= w else '가로형') \
          or {'x': .25, 'y': .05, 's': .5}
    s = max(16, round(box['s'] * w))
    x = round(box['x'] * w)
    y = round(box['y'] * h)
    x = max(0, min(x, w - s)); y = max(0, min(y, h - s))   # 이미지 밖으로 나가지 않게
    return im.crop((x, y, x + s, y + s))


def main():
    force = '--force' in sys.argv
    want_face = '--faces' in sys.argv
    boxes, defaults = load_faces()
    targets = SIZES + ([FACE] if want_face else [])
    for sub, _, _ in targets:
        os.makedirs(os.path.join(SRC, sub), exist_ok=True)

    names = sorted(n for n in os.listdir(SRC)
                   if n.lower().endswith(EXTS) and os.path.isfile(os.path.join(SRC, n)))
    if not names:
        print('portfolio/ 에 이미지가 없습니다.'); return

    total_src = total_dst = 0
    made = skipped = 0

    for n in names:
        src  = os.path.join(SRC, n)
        ssz  = os.path.getsize(src)
        stem = os.path.splitext(n)[0]
        outs = [(os.path.join(SRC, sub, stem + '.webp'), w, q) for sub, w, q in targets]

        todo = [o for o in outs
                if force or not os.path.exists(o[0]) or os.path.getmtime(o[0]) < os.path.getmtime(src)]
        if not todo:
            total_src += ssz; total_dst += sum(os.path.getsize(o[0]) for o in outs)
            skipped += 1
            continue

        im = Image.open(src)
        if im.mode not in ('RGB', 'RGBA'):
            im = im.convert('RGBA' if 'A' in im.mode or im.mode == 'P' else 'RGB')
        w0, h0 = im.size
        face_dst = os.path.join(SRC, FACE[0], stem + '.webp')

        for dst, width, qual in todo:
            if dst == face_dst:                          # 얼굴: 잘라낸 뒤 정사각으로
                crop_face(im, n, boxes, defaults) \
                    .resize((width, width), Image.LANCZOS) \
                    .save(dst, 'WEBP', quality=qual, method=6)
            else:
                width = min(width, w0)                   # 원본보다 크게 키우지 않는다
                im.resize((width, max(1, round(h0 * width / w0))), Image.LANCZOS) \
                  .save(dst, 'WEBP', quality=qual, method=6)

        sizes = [os.path.getsize(o[0]) for o in outs]
        total_src += ssz; total_dst += sum(sizes); made += 1
        line = '  %-22s %6.1fMB ->  썸네일 %5.0fKB + 감상용 %6.0fKB' % (n, ssz/1048576, sizes[0]/1024, sizes[1]/1024)
        if want_face:
            line += ' + 얼굴 %5.0fKB' % (sizes[2]/1024)
        print(line)

    print('\n생성 %d장, 건너뜀 %d장' % (made, skipped))
    print('합계 %.1fMB -> %.1fMB  (%.1f%%로 감소)'
          % (total_src/1048576, total_dst/1048576, (total_dst/total_src*100) if total_src else 0))

if __name__ == '__main__':
    main()
