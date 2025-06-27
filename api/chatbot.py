from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel
import google.generativeai as genai
import os
from dotenv import load_dotenv

router = APIRouter()
# 환경 변수 로드
load_dotenv(dotenv_path="key.env")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if not GOOGLE_API_KEY:
    raise Exception("GOOGLE_API_KEY 환경 변수가 설정되지 않았습니다.")

# Google Generative AI 구성
genai.configure(api_key=GOOGLE_API_KEY)

# GenerativeModel 초기화
model = genai.GenerativeModel(
    'gemini-2.5-flash-preview-05-20',
    #AI 모델의 역할 부여 
    system_instruction="""
        너의 이름은 "에이닥"이야 너는 환자들의 증상에 맞춰 설명을 해주고, 그에 따라 알맞은 병원과 약국들을 추천해주는 역할이야. 
        항상 친절하고 이해하기 쉽게 설명해줘.
    """
)

# 요청 모델 정의
class ChatRequest(BaseModel):
    prompt: str
    lang: str = "ko"  # 기본값 한국어

@router.post("/chat/")
async def chat(request: ChatRequest):
    try:
        user_prompt = request.prompt
        lang = request.lang

        # 언어별 system_instruction
        if lang == "en":
            system_instruction = (
                'Your name is "Aidoc". You are a calm and helpful assistant. When users describe their symptoms, give clear and concise explanations, and recommend appropriate hospitals or pharmacies if needed. Respond in a friendly, natural, and conversational tone. Avoid being overly enthusiastic.'
            )
        elif lang == "ja":
            system_instruction = (
                'あなたの名前は「エイドク」です。あなたは落ち着いて親切なアシスタントです。ユーザーが症状を説明したら、分かりやすく簡潔に説明し、必要に応じて適切な病院や薬局を案内してください。丁寧で自然な会話口調で答えてください。過度に感情的にならないようにしてください。'
            )
        else:  # default: Korean
            system_instruction = (
                '너의 이름은 "에이닥"이야. 너는 차분하고 친절한 어시스턴트야. 사용자가 증상을 설명하면, 명확하고 간결하게 설명해주고, 필요하다면 적절한 병원이나 약국을 추천해줘. 너무 과장되지 않게, 자연스럽고 대화하듯이 답변해줘.'
            )

        # 모델 생성 (system_instruction을 동적으로 적용)
        model = genai.GenerativeModel(
            'gemini-2.5-flash-preview-05-20',
            system_instruction=system_instruction
        )

        response = model.generate_content(
            user_prompt,
            generation_config=genai.types.GenerationConfig(
                candidate_count=1,
                temperature=0.7
            )
        )

        # 응답 처리
        if response.candidates and response.candidates[0].content.parts:
            generated_text = ''.join([part.text for part in response.candidates[0].content.parts])
        else:
            raise HTTPException(status_code=500, detail="유효한 응답 내용을 찾을 수 없습니다.")

        return {"reply": generated_text.strip()}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"서버 내부 오류: {str(e)}")