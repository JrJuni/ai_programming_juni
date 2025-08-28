# Streamlit UI & 파이프라인 오케스트레이션
# src/app.py
import streamlit as st
from typing import Optional, Dict, Any
from datetime import datetime
import io

from schema import ExtractionBundle, ExtractedConsultation, ExtractedContact
from schema import bundle_to_consultation, bundle_to_contact
from db import (
    init_migrate, insert_consultation, insert_contact,
    get_or_create_company_by_name, fetch_consultations_for_export
)

# 상단 import에 추가
from revision import parse_command_to_patch, apply_patch
try:
    from asr import transcribe_bytes  # 아직 미구현이면 except로 텍스트 입력만 사용
except Exception:
    transcribe_bytes = None


# ====== 초기 설정 ======
st.set_page_config(page_title="Expo Agent", page_icon="🎤", layout="wide")
if "ui_step" not in st.session_state:
    st.session_state.ui_step = 1
if "audio_bytes" not in st.session_state:
    st.session_state.audio_bytes = None
if "transcript" not in st.session_state:
    st.session_state.transcript = ""
if "stt_conf" not in st.session_state:
    st.session_state.stt_conf = None
if "lang" not in st.session_state:
    st.session_state.lang = "ko"
if "bundle" not in st.session_state:
    st.session_state.bundle = None
if "dev_mode" not in st.session_state:
    st.session_state.dev_mode = False

init_migrate()

# ====== 사이드바 ======
with st.sidebar:
    st.header("설정")
    st.session_state.dev_mode = st.toggle("개발자 모드", value=False, help="원본 음성/문장 디버깅용 UI 표시")
    mode = st.radio("요약/정리 모드", options=["offline", "openai", "anthropic"], horizontal=True)
    st.caption("오프라인: Exaone 3.5 2.4B (llama.cpp), 온라인: OpenAI/Anthropic")

st.title("🎤 전시장 상담 기록 Agent")

# ====== STEP 1: 녹음/업로드 & STT ======
if st.session_state.ui_step == 1:
    st.subheader("Step 1. 녹음/업로드 → STT")
    col1, col2 = st.columns([1,1])
    with col1:
        audio = st.audio_input("여기에 음성을 녹음하세요", help="브라우저 지원이 불안정하면 파일 업로드 탭을 이용")
    with col2:
        file = st.file_uploader("또는 오디오 파일 업로드 (wav/mp3/m4a)", type=["wav", "mp3", "m4a"])

    if audio:
        st.session_state.audio_bytes = audio.getvalue()
    elif file:
        st.session_state.audio_bytes = file.read()

    if st.session_state.audio_bytes:
        if st.session_state.dev_mode:
            st.audio(st.session_state.audio_bytes, format="audio/wav")

        # --- STT 호출부 (실제 구현 연결 예정) ---
        # 아래는 자리표시자: 실제로는 asr.transcribe_bytes(...) 호출
        transcript = "예시: day 1 오전 - ai 추진중, 본주 명함 전달. 스마트팩토리 불량검사, 1080p 20fps, 모델은 Yolo_v12_seg 제안."
        st.session_state.transcript = transcript
        st.session_state.stt_conf = 0.92
        st.session_state.lang = "ko"
        # ---------------------------------------

        st.success("STT 완료")
        if st.button("다음(요약/정리로)", type="primary"):
            st.session_state.ui_step = 2
            st.rerun()
    else:
        st.info("녹음하거나 파일을 업로드하세요.")

# ====== STEP 2: 요약/정리(보고서) ======
elif st.session_state.ui_step == 2:
    st.subheader("Step 2. 요약/정리 보고서")
    st.caption("이 단계에서는 간단 요약만 보여줍니다. 실제 DB 입력은 다음 단계에서 미리보기 후 저장합니다.")

    transcript = st.session_state.transcript

    # --- 요약/정리 호출부 (실제 구현 연결 예정) ---
    # summarize_and_extract(transcript, mode) → (bundle, debug)
    # 자리표시자:
    bundle = ExtractionBundle(
        consultation=ExtractedConsultation(
            source="ISEC2025",
            company_name="LG",
            comments="day 1 오전 - ai 추진중, 본주 명함 전달",
            field="스마트팩토리",
            ai_functions="불량검사",
            requirements=["해상도 1080에서 Yolo_v12_seg 20fps"],
            ai_models=["Yolo_v12"],
            next_action="",
            lang=st.session_state.lang
        ),
        contact=ExtractedContact(
            name="정상화",
            job_title="부팀장",
            phone="",
            email=None
        )
    )
    st.session_state.bundle = bundle
    # -------------------------------------------

    # 간단 보고서 카드
    with st.container(border=True):
        st.markdown(f"**회사**: {bundle.consultation.company_name or '-'}")
        st.markdown(f"**도메인**: {bundle.consultation.field or '-'} / **AI 기능**: {bundle.consultation.ai_functions or '-'}")
        st.markdown(f"**요구사양**: {'; '.join(bundle.consultation.requirements) or '-'}")
        st.markdown(f"**모델 후보**: {'; '.join(bundle.consultation.ai_models) or '-'}")
        st.markdown(f"**코멘트**: {bundle.consultation.comments or '-'}")
        if bundle.contact and (bundle.contact.name or bundle.contact.email or bundle.contact.phone):
            st.markdown(f"**담당자**: {bundle.contact.name or '-'} / {bundle.contact.job_title or '-'}")

        if st.session_state.dev_mode:
            c1, c2 = st.columns(2)
            with c1:
                if st.button("원본 음성 듣기"):
                    st.audio(st.session_state.audio_bytes, format="audio/wav")
            with c2:
                if st.button("원본 문장 보기"):
                    with st.expander("Transcript"):
                        st.write(st.session_state.transcript)
                        st.caption(f"lang={st.session_state.lang}, stt_conf={st.session_state.stt_conf}")

    if st.button("다음(테이블 입력 미리보기)", type="primary"):
        st.session_state.ui_step = 3
        st.rerun()

# ====== STEP 3: DB 입력 미리보기(편집 가능 + 음성 수정) ======
elif st.session_state.ui_step == 3:
    st.subheader("Step 3. 테이블 입력 미리보기 & 수정")

    bundle = st.session_state.bundle
    # 프리뷰 dict 생성
    consult_preview = bundle_to_consultation(bundle)
    base_doc = {
        "source": consult_preview.source or "",
        "company_name": consult_preview.company_name or "",
        "comments": consult_preview.comments or "",
        "field": consult_preview.field or "",
        "ai_functions": consult_preview.ai_functions or "",
        "requirements": consult_preview.requirements or [],
        "ai_models": consult_preview.ai_models or [],
        "next_action": consult_preview.next_action or "",
    }

    # 세션 상태에 편집용 문서 저장
    if "edit_doc" not in st.session_state:
        st.session_state.edit_doc = base_doc
    doc = st.session_state.edit_doc

    # ---- 표 편집(엑셀 느낌) : 리스트는 세미콜론 문자열로 보여주고 저장 시 split ----
    import pandas as pd
    row = {
        "Source": doc["source"],
        "Company": doc["company_name"],
        "Comments": doc["comments"],
        "Field": doc["field"],
        "AI Functions": doc["ai_functions"],
        "Requirements(;로 구분)": "; ".join(doc["requirements"]),
        "AI Models(;로 구분)": "; ".join(doc["ai_models"]),
        "Next Action": doc["next_action"],
    }
    st.caption("표 직접 편집")
    edited_df = st.data_editor(pd.DataFrame([row]), num_rows="fixed", use_container_width=True)
    edited = edited_df.iloc[0].to_dict()

    # ---- 음성 수정(자연어 → patch 적용) ----
    with st.expander("🎙️ 음성/텍스트로 수정 지시하기", expanded=False):
        colA, colB = st.columns(2)
        with colA:
            voice = st.audio_input("수정 음성 녹음")
        with colB:
            manual_cmd = st.text_input("또는 텍스트로 수정 지시 입력", placeholder="예) 회사명을 현대자동차로 바꿔 / 요구사양에 25fps 추가")

        if st.button("수정 지시 적용"):
            cmd_text = ""
            if voice and transcribe_bytes:
                try:
                    tr = transcribe_bytes(voice.getvalue(), lang_hint="ko")
                    cmd_text = tr["text"]
                    st.info(f"인식된 수정 명령: {cmd_text}")
                except Exception as e:
                    st.warning(f"STT 실패로 텍스트 입력만 사용하세요. 에러: {e}")
            if not cmd_text:
                cmd_text = manual_cmd.strip()

            if cmd_text:
                ops = parse_command_to_patch(cmd_text)
                # 리스트 필드는 문자열 → 리스트로 변환 규칙 유지
                patched = apply_patch(
                    {
                        **doc,
                        "requirements": doc.get("requirements", []),
                        "ai_models": doc.get("ai_models", []),
                    },
                    ops
                )
                st.session_state.edit_doc = patched
                st.rerun()
            else:
                st.warning("수정 명령이 비어 있습니다.")

    # ---- 저장 버튼: edited(표 수정)와 edit_doc(음성 수정 결과)을 병합 ----
    if st.button("저장", type="primary"):
        # 우선: 표 편집 반영
        doc["source"] = edited.get("Source", "") or ""
        doc["company_name"] = edited.get("Company", "") or ""
        doc["comments"] = edited.get("Comments", "") or ""
        doc["field"] = edited.get("Field", "") or ""
        doc["ai_functions"] = edited.get("AI Functions", "") or ""
        # 세미콜론 분할
        def _split(s): 
            import re
            return [p.strip() for p in re.split(r"[;,]", s or "") if p.strip()]
        doc["requirements"] = _split(edited.get("Requirements(;로 구분)", ""))
        doc["ai_models"] = _split(edited.get("AI Models(;로 구분)", ""))
        doc["next_action"] = edited.get("Next Action", "") or ""

        # DB 저장
        # 회사 id 생성/연결
        new_company_id = get_or_create_company_by_name(doc["company_name"]) if doc["company_name"] else None

        # 연락처는 이번 단계에선 생략(원하면 위에 data_editor 추가 가능)
        consult_id = insert_consultation({
            "source": doc["source"] or None,
            "company_id": new_company_id,
            "company_name": doc["company_name"] or None,
            "comments": doc["comments"] or None,
            "field": doc["field"] or None,
            "ai_functions": doc["ai_functions"] or None,
            "requirements": doc["requirements"],
            "ai_models": doc["ai_models"],
            "next_action": doc["next_action"] or None,
            "stt_conf": st.session_state.stt_conf,
            "transcript": st.session_state.transcript,
            "lang": st.session_state.lang,
        })
        st.success(f"저장 완료! consultation id = {consult_id}")
        # 상태 초기화(새 입력을 위해)
        for k in ("edit_doc", "bundle", "transcript", "audio_bytes"):
            st.session_state.pop(k, None)
        st.session_state.ui_step = 1
        st.rerun()
