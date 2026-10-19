# 제3자 글꼴·자료 출처 및 라이선스 고지

이 프로젝트(HWP/HWPX/HTML/PDF 변환 공장)가 쓰거나 참고한 글꼴·자료의 출처와 조건을 적는다. 법률 자문이 아니며, 확인하지 못한 것은 "확인 못 함"으로 적었다. 마지막 정리: 2026-10-16.

## 1. 앱 이미지에 설치되어 PDF 에 글자 모양이 쓰이는 글꼴 (배포·내장 대상)

각 버전의 `Dockerfile` 이 Debian 패키지로 설치한다(`fonts-nanum fonts-liberation fonts-crosextra-carlito fonts-crosextra-caladea fonts-dejavu-core`; 이미지에는 `fonts-dejavu-mono` 도 함께 설치되어 있다). 각 패키지의 저작권·라이선스 전문은 이미지 안 `/usr/share/doc/<패키지>/copyright` 에 그대로 들어 있다(2026-10-14 확인). 글꼴 파일은 **수정하지 않고** 쓰며, 변환 결과 PDF 에는 쓰인 글자만 부분 집합으로 박힌다.

| 글꼴 | 패키지(설치 버전) | 저작권 표시(패키지·글꼴 파일 원문) | 라이선스 | 원본 출처 |
|---|---|---|---|---|
| 나눔고딕 NanumGothic<br>나눔명조 NanumMyeongjo<br>나눔바른고딕 NanumBarunGothic<br>나눔고딕코딩 NanumGothicCoding<br>나눔스퀘어 NanumSquare·NanumSquareRound | `fonts-nanum` 20200506-1 | Copyright (c) 2010, NAVER Corporation (http://www.nhncorp.com), with Reserved Font Name Nanum, Naver Nanum, NanumGothic, NanumMyeongjo, NanumBarunGothic 등. 글꼴 파일 표기: NanumGothic ©2011 NHN Corporation(디자인 Sandoll Communications Inc.), NanumMyeongjo ©2010 NHN Corporation(디자인 FONTRIX), NanumBarunGothic ©2013 NHN Corporation(디자인 FONTRIX Inc.), NanumGothicCoding ©2009 NHN Corporation(디자인 Sandoll), NanumSquare ©2016·NanumSquareRound ©2017 NAVER Corporation(디자인 Sandoll) | SIL Open Font License 1.1 | http://hangeul.naver.com/ |
| Liberation Sans·Serif·Mono | `fonts-liberation` 1:2.1.5-3 | Digitized data copyright (c) 2010 Google Corporation with Reserved Font Arimo, Tinos and Cousine. Copyright (c) 2012 Red Hat, Inc. with Reserved Font Name Liberation. (디자인 Steve Matteson, Ascender Corporation) | SIL OFL 1.1 | https://github.com/liberationfonts |
| Carlito | `fonts-crosextra-carlito` 20230309-2 | Copyright (c) 2010-2013 by tyPoland Lukasz Dziedzic with Reserved Font Name "Carlito" (글꼴 파일: Copyright 2013 The Carlito Project Authors) | SIL OFL 1.1 | https://github.com/googlefonts/carlito |
| Caladea | `fonts-crosextra-caladea` 20200211-2 | Copyright 2012 The Caladea Project Authors (Carolina Giovagnoli and Andres Torresi, Huerta Tipografica) | SIL OFL 1.1 | https://github.com/huertatipografica/Caladea |
| DejaVu Sans·Serif·Sans Mono | `fonts-dejavu-core` 2.37-8, `fonts-dejavu-mono` 2.37-8 | Copyright (c) 2003 by Bitstream, Inc. All Rights Reserved. Bitstream Vera is a trademark of Bitstream, Inc. DejaVu changes are in public domain. (일부 글리프 Copyright (c) 2006 by Tavmjong Bah, Arev) | Bitstream Vera License | https://dejavu-fonts.github.io/ |

**조건과 지키는 방법**
- **SIL OFL 1.1**: 글꼴 자체를 단독으로 팔 수 없고, 글꼴을 재배포할 때는 저작권 표시와 라이선스를 함께 둬야 한다(공식 문구: "provided that each copy contains the above copyright notice and this license"). 수정본은 예약 글꼴 이름(Reserved Font Name)을 쓸 수 없다. **글꼴로 만든 문서에는 라이선스가 적용되지 않는다**("The requirement for fonts to remain under this license does not apply to any document created using the fonts or their derivatives"). → 우리는 글꼴을 수정하지 않고, 이미지에 라이선스 전문(`/usr/share/doc/*/copyright`)이 들어 있으며, OFL 글꼴로 만든 PDF 결과물에는 별도 고지 의무가 없다(DejaVu 의 Bitstream Vera 문구에는 문서 임베딩에 대한 별도 설명이 없어 확인 못 함 — 이 글꼴은 대체 글꼴로 드물게 쓰인다). 공식 문구: https://openfontlicense.org/open-font-license-official-text/
- **Bitstream Vera(DejaVu)**: 저작권·상표 고지와 허가 문구를 모든 복사본에 포함, 글꼴 단독 판매 금지, 수정하면 "Bitstream"·"Vera"가 들어간 이름을 쓰지 않는다. 같은 방식으로 지킨다.
- 나눔 글꼴 파일의 라이선스 이름 칸은 "NHN Corporation"처럼 회사 이름만 적혀 있고, OFL 1.1 이라는 표기는 Debian 패키지의 `copyright` 파일이 한다(NanumGothicCoding 은 글꼴 파일에도 OFL 1.1 이 적혀 있음). 네이버 공식 안내 페이지(`hangeul.naver.com`)는 이 환경에서 열 수 없어 직접 확인하지 못했다.

## 2. 우리 이미지에 없고 이름·측정만 참조하는 한컴 글꼴

변환 결과의 글꼴 이름(`font-family`)과 한컴 PDF 에서 잰 글자 폭 보정(`HANGUL_DELTA`)에 이름이 나온다. **글꼴 파일은 저장소·이미지·결과물에 넣지 않는다.** 한컴 PDF 는 글자 위치를 읽는 데만 쓰고 글꼴 데이터는 가져오지 않는다.

**함초롬바탕·함초롬돋움 (함초롬체)** — 글꼴 파일(한컴오피스 2024 설치본 `HANBatang.ttf`·`HANDotum.ttf`, Version 2.002 Build 20160224)이 스스로 적은 것(2026-10-14 읽음):
- 저작권: `Copyright (c) 2010-2015 Hancom INC(HNC). All rights reserved.`(돋움은 2010-2014)
- 상표: `HCR Batang is a trademark of YoonDesign.` 제작사 `YoonDesign`, 디자이너 필드 `Hancom Inc.`, 라이선스 칸 `YoonDesign Inc.`, URL `http://yoonfont.co.kr/` → **한글과컴퓨터와 윤디자인 두 이름이 파일에 들어 있다.**
- 내장 허용 표시(OS/2 fsType) = 8(편집 가능 내장 허용).
- **글꼴 파일 안에는 이용 조건 문구가 없다.** 조건은 한컴이 따로 공개한 안내에 의존한다.

이용 조건(한컴 원문은 직접 열지 못했고 아래는 요약·전달 자료다):

| 자료 | 내용 |
|---|---|
| 사용자가 확인해 알려 준 안내문(출처 URL 미상) | "저작권자: 한글과컴퓨터(윤디자인과 공동 개발). 개인·기업 모두 상업적 목적 포함 무료(인쇄물·웹사이트·영상·광고·BI/CI). 글꼴 출처 표기 권장" |
| 위키백과(한컴 2010 문서 "한컴오피스 2010 대표글꼴 함초롬체" 인용) | 윤디자인연구소와 한글과컴퓨터가 개발, 한컴 배포, 2010-02-17 공개. 개인·기업 무료, 모든 출판물·저작물에 자유 사용. 상업적 목적의 배포·수정은 하지 않음 |
| 나무위키·눈누(noonnu) | 임베딩 포함 자유 사용, **출처 표기는 '권장'(의무 아님)**, 글꼴 판매 금지, 상업적 배포·수정 금지(눈누 요약 안에서도 수정 항목이 서로 어긋남) |
| 한경 기사(2016) | "한컴오피스 안에서만 상업적 이용 허용"이라는 한컴 입장 전달 — 위 요약들과 **어긋남** |

한컴 서체 공식 페이지(https://font.hancom.com/pc/sub/sub3_1.php)는 **함초롬체를 다루지 않는다**(한컴 산스체·말랑말랑체·훈민정음 세로쓰기체: 상업적 사용·PDF 제작·임베딩 허용, 수정·재배포 불가, 판매 금지, 인쇄물·광고 이미지를 한컴이 프로모션에 활용할 수 있음). 한컴 다운로드 센터(https://www.hancom.com/support/downloadCenter/download)에서도 함초롬체 항목과 이용 조건을 찾지 못했다.

**출처 표기 문구**(밝힐 때): "글꼴 출처: 한글과컴퓨터·윤디자인 함초롬체(Copyright (c) 2010-2015 Hancom INC(HNC); https://www.hancom.com)". 지금은 함초롬체를 내장·배포하지 않으므로 결과물에 이 문구를 넣지는 않는다.

## 3. 이름만 참조하는 그 밖의 글꼴 — 글꼴 파일이 스스로 적은 저작권·내장 표시

말뭉치 문서 150건에서 쓰인 글꼴 중 위 절에 없는 것. 우리는 파일을 가지지도 배포하지도 않고, 이름을 대체 글꼴 선택과 폭 보정 표에 쓸 뿐이다. 아래는 **이 PC(Windows·한컴오피스 2024)에 설치된 글꼴 파일의 이름 테이블**을 2026-10-14 에 읽은 값이다(1차 자료). fsType: 0 = 설치형(제한 없음), 4 = 미리보기·인쇄, 8 = 편집 가능, 2 = 내장 금지.

| 글꼴(문서 이름) | 파일 | 글꼴 파일의 저작권·상표 | 글꼴 파일 안의 이용 조건 | fsType |
|---|---|---|---|---|
| 맑은 고딕 | malgun.ttf v6.69 | © 2022 Microsoft Corporation(디자이너 Kyoung-bae Lee·Daekwon Kim, http://www.sandoll.co.kr) | "Microsoft supplied font. You may use this font to create, display, and print content as permitted by the license terms or terms of use, of the Microsoft product, service, or content in which this font was included. You may only (i) embed this font in content as permitted by the embedding restrictions included in this font; and (ii) temporarily download this font to a printer or other output device to help print content. Any other use is prohibited." | 8 |
| 바탕(Batang)·굴림(Gulim) | batang.ttc·gulim.ttc | © HanYang I&C Co., LTD.(2000·2009), "registered trademark of the Microsoft Corporation" | 위 맑은 고딕과 같은 Microsoft supplied font 문구 | 8 |
| Times New Roman·Arial·Courier New | times.ttf 등 | © The Monotype Corporation | Microsoft supplied font 문구 | 8 |
| 한컴바탕(Haansoft Batang)·한컴돋움(Haansoft Dotum) | HBATANG.TTF·HDOTUM.TTF v1.21 | (c) Copyright HanYang I&C Co.,Ltd. 2004, registered trademark of the Hanyang I & C | 없음 | 0 |
| 한양 계열: 한양중고딕(HYGothic-Medium)·HY헤드라인M(HYHeadLine-Medium)·한양신명조(HYSinMyeongJo-Medium)·HY견명조·HY그래픽·HY울릉도·HY수평선 등 | H2*.TTF, HY*.TTF | (c) Copyright HanYang Systems Inc. 1995 / HanYang I&C Co.,Ltd. 2002~2003, registered trademark of HanYang | 없음 | 0 |
| 휴먼명조·휴먼고딕·휴먼옛체·안상수체(굵은·가는·중간)·팸체·샘체 | HMK*.TTF | "HUMAN LICENSE TO HANGUL&COMPUTERS" (이 문구만 있음. 구형 HMFM*·HMKM* 파일은 Copyright(c) 1996 Human Computers, Inc.) | 없음 | 0(구형은 8) |
| 윤고딕(한컴 윤고딕·Haan YoonGothic 720~760)·한컴 백제·소망·쿨재즈·세일·솔잎·윤헤드 등 | HANYoonGothic*.ttf, HAN*.ttf | Copyright © 2012-2013(또는 1989-2009) YoonDesign Inc. All rights reserved. 윤고딕 라이선스 URL http://www.YoonDesign.com/license | 없음(URL 만) | **4(미리보기·인쇄 — 문서 내장 편집은 제한)** |
| 안상수체 ahn2006 | ahn_*.ttf | `Copyright` 한 단어뿐 | 없음 | 4 |

- **우리에게 의미하는 것**: 이 글꼴들은 글꼴 파일을 받지 않고 배포하지 않으므로 조건이 우리 이미지에는 적용되지 않는다. 다만 V3 가 이 글꼴들을 PDF 에 **내장**하기로 하면 fsType 과 위 문구(특히 Microsoft 글꼴의 "embedding restrictions", 윤고딕의 fsType 4)를 지켜야 한다.
- 한컴오피스는 자기가 번들한 제3자 글꼴(Baloo·Diplomata·Limelight·Oleo Script·Vast Shadow = SIL OFL 1.1, Rochester·Schoolbell = Apache-2.0, Nanum Brush = NHN)에는 `Shared/TTF/All/notice/` 폴더에 `*_notice.txt`·`*_copying.txt` 를 두었다. 한컴 자기 글꼴(함초롬·한컴바탕 등)의 조건 문서는 그 폴더에서 찾지 못했다.
- **이 PC 에서 찾지 못한 글꼴**(문서 이름 기준): 한컴 고딕(HancomGothic), 신명 중명조·신명 중고딕·신명 신명조, HCI Poppy, 양재튼튼체, '-윤명조110'·'-윤고딕120' 같은 옛 윤 글꼴(위 표의 Haan YoonGothic 과는 다른 파일). 이들의 저작권·조건은 확인하지 못했다.
- Liberation Sans·Serif·Mono 는 Arial·Times New Roman·Courier New 과 글자 폭이 같게 만들어진 글꼴이라 대신 쓴다(위 1절).

## 4. rhwp (MIT) — 폭표 숫자 사용 + 구조·알고리즘 참고

- 저장소: https://github.com/edwardkim/rhwp (v0.8.7, 2026-10-06 판을 `corpus/_ref/rhwp_src` 에 받아 읽었다) — **MIT License, Copyright (c) 2025-2026 Edward Kim**
- **가져온 데이터(2026-10-14, 사용자 결정 "글자 폭 숫자는 괜찮을 것 같아")**: `src/renderer/font_metrics_generated.rs`·`font_metrics_overlays.rs` 의 글꼴 폭표(글자 폭 숫자) 608항목을 `versions/V3/devtools/extract_rhwp_metrics.py` 로 JSON 으로 옮겨 `versions/V3/core/data/rhwp_font_metrics.json.gz` 에 넣었다. **우리 한컴 PDF 측정이 있는 값은 측정이 우선이고 rhwp 숫자는 빈자리 채움·대조용이다.**
  - **출처 주의**: rhwp 자신의 출처 기록(`mydocs/tech/investigations/issue-4964/font_metric_lineage_manifest.json`)은 600항목 중 원본 글꼴이 확정된 것 0, 출처 불명 595, 나머지 5(한양신명조 등)는 한컴 COM 으로 잰 값이라고 한다. rhwp 의 `ttfs/FONTS.md` 는 폭 값이 한컴 글꼴 파일에서 추출한 것이고 "수치는 저작권 대상이 아니다"라는 것이 개발자의 입장이라고 적는다(법적 판단 아님). 우리는 글꼴 파일을 가져오지 않았다.
- **구조·알고리즘은 읽고 우리 코드로 새로 썼다**(코드를 옮기지 않았다): 줄 나눔 토큰화·금칙 문자 집합·줄 끝 공백 매달기·내어쓰기 줄 폭·글자 폭 계산식(`versions/V3/core/linebreak.py`·`widthmodel.py`·`metrics.py`). 한글 줄 나눔 비트 해석(비트 7 = 1 이 글자 단위)과 일부 글자 폭 규칙(반각 형태·따옴표·기호)도 rhwp 의 설명과 한컴 PDF 실측으로 확인해 반영했다. 참고만 했으므로 표시는 의무가 아니지만 밝혀 둔다.

```
MIT License

Copyright (c) 2025-2026 Edward Kim

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## 5. 한컴 공개 자료

HWP 5.0 파일 형식은 한글과컴퓨터가 공개한 문서를 바탕으로 했고(rhwp 정오표 참고), HWPX 열거는 한컴의 공개 `hwpx-owpml-model`(Apache-2.0)을 참고했다. "한글", "한컴", "HWP", "HWPX"는 주식회사 한글과컴퓨터의 등록 상표이며, 이 프로젝트는 한글과컴퓨터와 제휴·후원·승인 관계가 없다.

## 6. 이 PC 에 설치된 글꼴 파일에서 직접 읽은 폭표 (2026-10-16)

- `versions/V3/devtools/build_font_metrics.py` 가 이 개발 PC(Windows 11, 한컴오피스 2024)에 설치된 글꼴 파일(`C:\Windows\Fonts`)의 `hmtx`(글자 폭) 숫자만 읽어 `versions/V3/core/data/font_metrics_local.json.gz` 를 만든다. **글꼴 파일·글리프 모양은 저장소·이미지·결과물에 넣지 않는다.** 글꼴 하나는 (이름, 굵기, 기울임)이 파일의 전체 이름·macStyle 과 정확히 맞을 때만 쓰고, 가변 글꼴은 쓰지 않는다.
- 결과 377항목: rhwp 표의 353항목(함초롬바탕·함초롬돋움·맑은 고딕·바탕·굴림·돋움 등)을 다시 만들어 **값이 rhwp 표와 같음(차이 0.0000em)을 확인**했고, rhwp 표에 없던 24항목(궁서 등 시험 문서에 쓰인 글꼴)을 더했다. 이 377항목에는 rhwp 값을 쓰지 않는다(`core/metrics.py` 가 글꼴 파일 표를 먼저 본다). 이 변경 전후 평가는 문서별로 달라진 것이 0건, 줄 나눔 재현율 92.7% 그대로다.
- **rhwp 값이 남는 것**: 글꼴 파일 값이 rhwp 값과 다른 7항목(한양·휴먼 계열 — 한컴이 글꼴에 없는 글자를 다른 글꼴로 대체해 잰 값일 수 있다)과 이 PC 에 없는 글꼴 등 253항목. 시험 문서에 쓰인 글꼴 153종 중 15종(문서 사용 횟수 18%: 한양신명조·한양중고딕·휴먼명조·한양견명조·한컴돋움·한양견고딕 등)이 여기에 해당한다. 이 부분에는 4절의 MIT 고지가 계속 적용된다.
- 글꼴 파일에서 폭 숫자를 읽는 것이 각 글꼴의 사용 조건(Microsoft "Microsoft supplied font…", 한컴·한양·휴먼 글꼴 조건 등)에 어떤 의미인지는 **법률 검토를 받지 못했다**(확인 못 함). 숫자만 쓰고 글꼴·글리프를 배포하지 않는 것으로 갈음했다.
