"""
AI 수학 풀이 도우미 — Streamlit Cloud 버전
"""

import base64
import json
import re

import anthropic
import streamlit as st

# ─── 페이지 설정 ────────────────────────────────────────────────
st.set_page_config(
    page_title="AI 수학 풀이 도우미",
    page_icon="📐",
    layout="wide",
)

# ─── 비밀번호 인증 ───────────────────────────────────────────────
def check_password() -> bool:
    if st.session_state.get("authenticated"):
        return True

    st.markdown("## 🔒 접근 제한")
    pw = st.text_input("비밀번호를 입력하세요", type="password")
    if st.button("확인"):
        correct = st.secrets.get("APP_PASSWORD", "")
        if pw == correct:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("비밀번호가 틀렸습니다.")
    return False

if not check_password():
    st.stop()

st.markdown("""
<style>
/* 전체 배경 */
[data-testid="stAppViewContainer"] { background: #f0f4ff; }
[data-testid="stSidebar"] { background: #ffffff; }

/* 헤더 숨기기 */
[data-testid="stHeader"] { display: none; }

/* 카드 스타일 */
.card {
    background: #ffffff;
    border: 1px solid #dbe4ff;
    border-radius: 10px;
    padding: 16px 20px;
    margin-bottom: 12px;
}
.ans-box {
    background: #e6fcf5;
    border: 2px solid #63e6be;
    border-radius: 10px;
    padding: 14px 20px;
    margin-bottom: 12px;
}
.formula-box {
    background: #fff9db;
    border: 2px solid #ffe066;
    border-radius: 10px;
    padding: 14px 20px;
    margin-bottom: 12px;
}
.sim-header {
    background: #dbe4ff;
    border-radius: 8px 8px 0 0;
    padding: 8px 14px;
    font-weight: bold;
    color: #5c7cfa;
}
.sim-card {
    background: #ffffff;
    border: 1px solid #dbe4ff;
    border-radius: 8px;
    margin-bottom: 14px;
    overflow: hidden;
}
h1 { color: #5c7cfa !important; }
</style>
""", unsafe_allow_html=True)

# ─── 카테고리 한글 ───────────────────────────────────────────────
CATEGORY_KO = {
    "algebra":    "대수 / 함수",
    "geometry":   "기하 / 도형",
    "calculus":   "미적분",
    "statistics": "확률 / 통계",
    "number":     "정수론",
    "linear":     "선형대수",
    "other":      "기타",
}

# ─── LaTeX → 평문 변환 ──────────────────────────────────────────
def plain(text: str) -> str:
    greek = {
        'alpha':'α','beta':'β','gamma':'γ','delta':'δ','epsilon':'ε',
        'zeta':'ζ','eta':'η','theta':'θ','iota':'ι','kappa':'κ',
        'lambda':'λ','mu':'μ','nu':'ν','xi':'ξ','pi':'π',
        'rho':'ρ','sigma':'σ','tau':'τ','phi':'φ','chi':'χ','psi':'ψ','omega':'ω',
        'Alpha':'Α','Beta':'Β','Gamma':'Γ','Delta':'Δ','Theta':'Θ',
        'Lambda':'Λ','Pi':'Π','Sigma':'Σ','Phi':'Φ','Omega':'Ω',
    }
    for en, sym in greek.items():
        text = text.replace(f'\\{en}', sym)

    symbols = [
        ('\\times','×'),('\\div','÷'),('\\pm','±'),('\\mp','∓'),
        ('\\leq','≤'),('\\geq','≥'),('\\neq','≠'),('\\approx','≈'),
        ('\\le','≤'),('\\ge','≥'),('\\ne','≠'),
        ('\\infty','∞'),('\\cdot','·'),('\\ldots','...'),('\\cdots','···'),
        ('\\because','∵'),('\\therefore','∴'),
        ('\\in','∈'),('\\notin','∉'),('\\subset','⊂'),
        ('\\cup','∪'),('\\cap','∩'),
        ('\\to','→'),('\\rightarrow','→'),('\\leftarrow','←'),
        ('\\Rightarrow','⇒'),('\\Leftrightarrow','⟺'),
        ('\\log','log'),('\\ln','ln'),('\\sin','sin'),('\\cos','cos'),
        ('\\tan','tan'),('\\lim','lim'),('\\sum','Σ'),('\\int','∫'),
        ('\\{','('),('\\}',')'),('\\|','|'),
        ('\\,',' '),('\\;',' '),('\\quad',' '),('\\qquad','  '),
        ('\\!',''),('\\ ',' '),('\\\\',' \n'),
    ]
    for latex, sym in symbols:
        text = text.replace(latex, sym)

    text = re.sub(r'\\(?:left|right)\s*([()[\]|.])', r'\1', text)
    text = re.sub(r'\\(?:left|right)\.', '', text)

    for _ in range(6):
        text = re.sub(r'\\sqrt\[([^\]]+)\]\{([^{}]*)\}', r'\1√(\2)', text)
        text = re.sub(r'\\sqrt\{([^{}]*)\}', r'√(\1)', text)
        text = re.sub(r'\\frac\{([^{}]*)\}\{([^{}]*)\}', r'(\1)/(\2)', text)
        text = re.sub(r'\^\{([^{}]*)\}', r'^\1', text)
        text = re.sub(r'_\{([^{}]*)\}', r'_\1', text)

    text = re.sub(r'\\[a-zA-Z]+\{([^{}]*)\}', r'\1', text)
    text = re.sub(r'\\[a-zA-Z]+\*?', '', text)
    text = re.sub(r'\$\$(.+?)\$\$', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'\$([^$\n]+)\$', r'\1', text)
    text = text.replace('$', '')
    text = text.replace('{', '').replace('}', '')
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

# ─── 프롬프트 ────────────────────────────────────────────────────
PLAIN_MATH_RULE = """
수식 표현 규칙 (반드시 지킬 것):
- LaTeX($, \\frac, \\sqrt 등) 절대 사용 금지
- 분수: a/b 형식 (예: (x+1)/(x-1))
- 제곱근: √ 기호 사용 (예: √2, √(x+1))
- 거듭제곱: ^ 사용 (예: x^2, (a+b)^3)
- 그리스문자: α β γ π θ 등 직접 입력
- 무한대: ∞, 부등호: ≤ ≥ ≠, 곱셈: ×"""

STYLE_RULE = """
설명 스타일 (정승재 선생님처럼):
- 핵심만 짧고 명확하게 — 불필요한 말 금지
- 어려운 용어 대신 쉬운 말로 ("인수분해" → "곱의 형태로 바꾸기")
- 각 단계는 2~3줄 이내로 간결하게
- "이 부분이 핵심이에요!", "여기서 실수 많이 해요!" 같은 친근한 강조 사용
- 왜 이렇게 하는지 이유를 한 문장으로 설명
- 학생 눈높이 — 중학생도 이해할 수 있는 표현
- 단계 수는 최소화 (3~5단계로 압축)"""

ANALYZE_PROMPT = """이 수학 문제 이미지를 분석하여 아래 JSON 형식으로만 응답하세요.
마크다운(```json) 없이 순수 JSON만 출력하세요.
""" + PLAIN_MATH_RULE + """

{
  "category": "algebra | geometry | calculus | statistics | number | linear | other",
  "difficulty": 난이도 숫자(1~5),
  "problemText": "문제 전체 내용을 그대로 텍스트로",
  "formulas": "이 문제에 반드시 필요한 공식/개념 (항목마다 줄바꿈, 2~4개, 쉬운 말로)",
  "answer": "최종 정답"
}

difficulty 기준: 1=중학기초, 2=쉬움, 3=고교보통, 4=수능, 5=경시대회"""

SOLVE_PROMPT = """당신은 수학 선생님 정승재입니다.
학생이 이해하기 쉽게, 핵심만 짧고 명확하게 설명하세요.
""" + PLAIN_MATH_RULE + STYLE_RULE + """

[문제]
{problem}

아래 형식으로 작성하세요:

■ 핵심 포인트
(이 문제의 핵심을 딱 한 줄로!)

■ 풀이
1단계: (짧고 명확하게)
2단계: (짧고 명확하게)
3단계: (짧고 명확하게)
(최대 5단계까지)

■ 자주 하는 실수
(여기서 많이 틀려요! — 한 줄로)

■ 답
{answer_placeholder}"""

ASK_PROMPT = """당신은 수학 선생님 정승재입니다.
학생이 이해하기 쉽게, 핵심만 짧고 명확하게 설명하세요.
""" + PLAIN_MATH_RULE + STYLE_RULE + """

[질문]
{question}

아래 형식으로 작성하세요:

■ 핵심 포인트
(딱 한 줄로!)

■ 풀이 / 설명
1단계:
2단계:
3단계:
(필요한 만큼, 최대 5단계)

■ 정리
(이것만 기억하세요! — 한 줄로)"""

SIMILAR_PROMPT = """아래 수학 문제와 같은 개념의 유사 문제 3개를 만들어주세요.
마크다운 없이 순수 JSON 배열만 출력하세요.
""" + PLAIN_MATH_RULE + """

[원본 문제]
{problem}

[형식]
[
  {{"problem": "문제 내용", "answer": "정답", "solution": "단계별 풀이 (3~4단계, 핵심만 짧게)"}},
  {{"problem": "문제 내용", "answer": "정답", "solution": "단계별 풀이 (3~4단계, 핵심만 짧게)"}},
  {{"problem": "문제 내용", "answer": "정답", "solution": "단계별 풀이 (3~4단계, 핵심만 짧게)"}}
]"""


# ─── API 클라이언트 ──────────────────────────────────────────────
def get_client() -> anthropic.Anthropic | None:
    # 1순위: Streamlit Cloud secrets
    key = st.secrets.get("ANTHROPIC_API_KEY", "") if hasattr(st, "secrets") else ""
    # 2순위: 사이드바 입력값
    if not key:
        key = st.session_state.get("api_key", "")
    if not key:
        st.error("왼쪽 사이드바에 API 키를 입력해주세요.")
        return None
    return anthropic.Anthropic(api_key=key)


# ─── 사이드바 ────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📐 AI 수학 풀이")
    st.divider()

    # API 키 (secrets에 없을 때만 입력란 표시)
    has_secret = bool(st.secrets.get("ANTHROPIC_API_KEY", "")) if hasattr(st, "secrets") else False
    if not has_secret:
        api_input = st.text_input(
            "🔑 Anthropic API Key",
            type="password",
            placeholder="sk-ant-...",
            value=st.session_state.get("api_key", ""),
        )
        if api_input:
            st.session_state["api_key"] = api_input
            st.success("✔ 저장됨")
    else:
        st.success("✔ API 키 설정됨")

    st.divider()
    st.caption("powered by Claude Opus 4.6")


# ─── 메인 ────────────────────────────────────────────────────────
st.markdown("# 📐 AI 수학 풀이 도우미")

# 이미지 업로드 (메인 화면 — 모바일 대응)
uploaded = st.file_uploader(
    "📷 수학 문제 이미지를 올려주세요",
    type=["jpg", "jpeg", "png", "webp", "bmp"],
    help="문제가 찍힌 사진이나 스크린샷을 올려주세요",
)
if uploaded:
    st.image(uploaded, use_container_width=True)

if uploaded:
    uploaded.seek(0)
    image_bytes = uploaded.read()
    b64 = base64.standard_b64encode(image_bytes).decode()
    mime = uploaded.type or "image/jpeg"

    # 이미지가 바뀌면 세션 초기화
    img_key = uploaded.name + str(len(image_bytes))
    if st.session_state.get("img_key") != img_key:
        st.session_state["img_key"] = img_key
        st.session_state.pop("analysis", None)
        st.session_state.pop("similar_list", None)

    # ── 버튼 행 ─────────────────────────────────────────────────────
    col_a, col_b, col_c = st.columns([1, 1, 2])
    do_solve   = col_a.button("📝 문제 풀이",    use_container_width=True, type="primary")
    do_similar = col_b.button("🎲 유사문제 조회", use_container_width=True,
                               disabled="analysis" not in st.session_state)
else:
    st.info("위에서 수학 문제 이미지를 업로드하거나, 아래 질문창에 직접 물어보세요.")
    do_solve = False
    do_similar = False
    b64 = mime = None

# ── 문제 풀이 ────────────────────────────────────────────────────
if do_solve:
    client = get_client()
    if client:
        # 1단계: 분석
        with st.spinner("AI가 문제를 분석하는 중..."):
            r = client.messages.create(
                model="claude-opus-4-6",
                max_tokens=1024,
                messages=[{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64",
                                                 "media_type": mime, "data": b64}},
                    {"type": "text", "text": ANALYZE_PROMPT},
                ]}],
            )
        raw = next((b.text for b in r.content if b.type == "text"), "{}")
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        try:
            analysis = json.loads(raw)
        except Exception:
            analysis = {"category": "other", "difficulty": 3,
                        "problemText": raw, "formulas": "", "answer": "분석 실패"}

        analysis["problemText"] = plain(analysis.get("problemText", ""))
        analysis["formulas"]    = plain(analysis.get("formulas", ""))
        analysis["answer"]      = plain(analysis.get("answer", ""))
        st.session_state["analysis"] = analysis
        st.session_state.pop("similar_list", None)

        # 2단계: 스트리밍 풀이
        ans_hint = f"답: {analysis['answer']}" if analysis.get("answer") else "위 풀이에서 확인"
        prompt = SOLVE_PROMPT.format(
            problem=analysis["problemText"],
            answer_placeholder=ans_hint,
        )
        with client.messages.stream(
            model="claude-opus-4-6",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            chunks = []
            for text in stream.text_stream:
                chunks.append(text)
            st.session_state["solution"] = plain("".join(chunks))

        st.rerun()  # 버튼 disabled 상태 갱신

# ── 결과 표시 ────────────────────────────────────────────────────
if "analysis" in st.session_state:
    a = st.session_state["analysis"]

    # 정보 행
    cat   = CATEGORY_KO.get(a.get("category", ""), "기타")
    diff  = int(a.get("difficulty", 3))
    stars = "★" * diff + "☆" * (5 - diff)

    m1, m2 = st.columns(2)
    m1.metric("분야", cat)
    m2.metric("난이도", stars)

    # 정답 박스
    st.markdown(f"""
    <div class="ans-box">
      <span style="font-size:1.05em;font-weight:bold;color:#20c997;">✅ 정 답&nbsp;&nbsp;</span>
      <span style="font-size:1.2em;font-weight:bold;color:#0a7554;">{a.get('answer') or '풀이 확인 필요'}</span>
    </div>
    """, unsafe_allow_html=True)

    # 핵심 공식/개념 박스
    st.markdown("**📚 이것만 알면 돼요! (핵심 공식/개념)**")
    st.markdown(f'<div class="formula-box"><pre style="margin:0;font-family:\'맑은 고딕\',sans-serif;white-space:pre-wrap;">{a.get("formulas","")}</pre></div>',
                unsafe_allow_html=True)

    # 단계별 풀이
    st.markdown("**🔢 단계별 풀이 (정승재 선생님 스타일)**")
    if "solution" in st.session_state:
        st.markdown(f'<div class="card"><pre style="margin:0;font-family:\'맑은 고딕\',sans-serif;white-space:pre-wrap;">{st.session_state["solution"]}</pre></div>',
                    unsafe_allow_html=True)
    else:
        st.caption("📝 문제 풀이 버튼을 눌러주세요.")

# ── 유사문제 조회 ─────────────────────────────────────────────────
if do_similar and "analysis" in st.session_state:
    client = get_client()
    if client:
        problem = st.session_state["analysis"]["problemText"]
        with st.spinner("유사 문제 3개 생성 중..."):
            r = client.messages.create(
                model="claude-opus-4-6",
                max_tokens=3000,
                messages=[{"role": "user", "content": SIMILAR_PROMPT.format(problem=problem)}],
            )
        raw = next((b.text for b in r.content if b.type == "text"), "[]")
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        try:
            st.session_state["similar_list"] = json.loads(raw)
        except Exception:
            st.session_state["similar_list"] = []

# ── 유사문제 표시 ─────────────────────────────────────────────────
if "similar_list" in st.session_state:
    sim_list = st.session_state["similar_list"]
    st.divider()
    st.markdown("## 🎲 유사 문제 3개")

    if not sim_list:
        st.warning("유사문제를 가져오지 못했습니다. 다시 시도해주세요.")
    else:
        for i, p in enumerate(sim_list):
            with st.expander(f"**문제 {i+1}**  —  정답: {plain(p.get('answer',''))}",
                             expanded=True):
                st.markdown(plain(p.get("problem", "")))

                if p.get("solution"):
                    st.markdown("**풀이**")
                    st.markdown(f'<div class="card"><pre style="margin:0;font-family:\'맑은 고딕\',sans-serif;white-space:pre-wrap;">{plain(p["solution"])}</pre></div>',
                                unsafe_allow_html=True)

# ── 수학 질문하기 ─────────────────────────────────────────────────
st.divider()
st.markdown("## 💬 정승재 선생님께 질문하기")
st.caption("이미지 없이 수학 개념이나 문제를 직접 물어보세요.")

question = st.text_area(
    label="질문 입력",
    placeholder="예) 이차방정식 근의 공식은 어떻게 유도해요?\n예) x^2 - 5x + 6 = 0 풀어줘",
    height=100,
    label_visibility="collapsed",
)

do_ask = st.button("✏️ 질문하기", type="primary", disabled=not question.strip())

if do_ask and question.strip():
    client = get_client()
    if client:
        prompt = ASK_PROMPT.format(question=question.strip())
        answer_box = st.empty()
        collected = []
        with st.spinner("정승재 선생님이 답변 중..."):
            with client.messages.stream(
                model="claude-opus-4-6",
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                for chunk in stream.text_stream:
                    collected.append(chunk)
        answer = plain("".join(collected))
        st.markdown(f'<div class="card"><pre style="margin:0;font-family:\'맑은 고딕\',sans-serif;white-space:pre-wrap;">{answer}</pre></div>',
                    unsafe_allow_html=True)
