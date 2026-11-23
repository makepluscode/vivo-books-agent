# S2 — 한국어 혼합 질의 검색

BrowserOS neo, Liner Search API Playground에서 실제 호출했어요.

쿼리: `랭체인 v1 LLMChain langchain-classic 공식 마이그레이션 import`

결과 수 설정: 5, 날짜 제한 없음.

## 반환 결과 (순서대로)

1. https://docs.langchain.com/oss/python/migrate/langchain-v1 — Python LangChain v1 migration guide.
2. https://activewizards.com/blog/surviving-langchain-version-upgrades-migration-patterns-for-production-systems/ — 비공식 마이그레이션 설명.
3. https://docs.langchain.com/oss/python/releases/langchain-v1 — 스니펫: Legacy functionality has moved to langchain-classic to keep the core packages lean.
4. https://docs.langchain.com/oss/javascript/migrate/langchain-v1 — JavaScript 문서, `@langchain/classic` 안내.
5. https://www.youtube.com/watch?v=SUzfebcOhiU — 비공식 영상.

## 판정

공식 Python 문서가 1위이고 3위 스니펫에 classic 이동이 명시돼요. 다만 JavaScript 안내와 비공식 설명도 함께 나왔어요. S1과 쿼리 내용 자체도 달라서, 언어만의 효과를 비교하는 통제 실험은 아니에요.
