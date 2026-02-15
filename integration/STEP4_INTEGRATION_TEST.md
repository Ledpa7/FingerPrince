# Step 4 - Integration & Testing Runbook

이 문서는 Server Vibe MVP의 E2E 통합 테스트 절차입니다.

## 0) 사전 조건
- Supabase SQL 실행 완료: `supabase_step1.sql`
- Agent 환경 설정 완료: `agent/.env`
- Web 환경 설정 완료: `web/.env.local`
- Supabase Auth에서 Anonymous Sign-In 사용 시 활성화

## 1) 실행
1. 터미널 A
```powershell
cd c:\Users\wjdwl\.codex\project\ServerVibe\agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env  # 최초 1회
python main.py
```

2. 터미널 B
```powershell
cd c:\Users\wjdwl\.codex\project\ServerVibe\web
copy .env.example .env.local  # 최초 1회
npm install
npm run dev
```

3. 모바일 브라우저 접속
- PC와 같은 네트워크에서 `http://<PC_IP>:3000`

## 2) 통합 테스트 시나리오
1. 기본 명령 실행
- 웹 입력: `whoami`
- 기대 결과:
  - `commands` 행 생성 (`status=pending`)
  - Agent가 `processing -> completed`로 업데이트
  - 채팅에 `response_log` 렌더링

2. 스크린샷 캡처
- 웹 입력: `/capture`
- 기대 결과:
  - Storage `screenshots/{user_id}/...png` 파일 생성
  - `image_url` 업데이트
  - 채팅 버블에 이미지 표시

3. 앱 실행
- 웹 입력: `/open notepad`
- 기대 결과:
  - 로컬 PC에서 앱 실행
  - `completed` + 실행 메시지 로그

4. 오류 처리
- 웹 입력: `this-command-does-not-exist`
- 기대 결과:
  - `status=error`
  - 오류 로그가 `response_log`에 기록

5. 원격 전환 버튼
- 웹 상단 `원격 접속` 버튼 클릭
- 기대 결과:
  - `https://remotedesktop.google.com/access/` 오픈

## 3) 확인용 SQL
- 파일: `integration/smoke_test_commands.sql`
- SQL Editor에서 user_id를 교체 후 실행

## 4) 합격 기준 (MVP)
- 텍스트 명령 왕복(latency 체감)이 안정적
- `/capture` 이미지가 3회 연속 정상 업로드
- 에러 명령이 앱 크래시 없이 `error` 상태로 처리
- 모바일 뷰에서 입력창/버블 레이아웃 깨짐 없음

## 5) 트러블슈팅
1. Web에서 명령 insert 실패
- RLS 정책과 `user_id = auth.uid()` 일치 확인
- 익명 로그인 미활성화 시 Auth 설정 확인

2. Agent가 반응 없음
- `SUPABASE_URL`, `SUPABASE_KEY(service_role)` 확인
- Realtime publication에 `commands` 포함 여부 확인

3. 스크린샷 업로드 실패
- storage bucket `screenshots` 존재 여부
- bucket policy 및 파일 경로(`{user_id}/...`) 확인
