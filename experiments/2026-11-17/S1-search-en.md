# S1 — 영어 공식 문서 검색

BrowserOS neo, Liner Search API Playground에서 실제 호출했어요.

쿼리: `site:docs.langchain.com LangChain v1 migration LLMChain langchain-classic`

결과 수 설정: 5, 날짜 제한 없음.

## 반환 결과 (순서대로)

1. https://docs.langchain.com/oss/python/migrate/langchain-v1 — LangChain v1 migration guide. 스니펫에 `LLMChain`, `ConversationChain` 포함.
2. https://docs.langchain.com/oss/python/releases/langchain-v1 — What's new in LangChain v1.
3. https://docs.langchain.com/oss/python/langchain/install — Install LangChain.
4. https://docs.langchain.com/oss/javascript/langchain/overview — JavaScript LangChain overview.
5. https://docs.langchain.com/oss/python/concepts/memory — Memory overview.

## 판정

공식 Python 마이그레이션 문서가 1위로 반환됐어요. 다섯 결과가 모두 해당 공식 도메인이지만, JavaScript 문서와 직접 관련 없는 문서도 섞였어요. 도메인만으로 충분한 근거라고 판단하면 안 돼요.

검색 스니펫 자체에는 `langchain-classic`으로 바꾸는 구체적 수정 근거가 충분히 나오지 않았어요. 후속 질의 또는 원문 확인이 필요해요.

실제 Python 코드 실행 및 수정 성공을 확인한 실험은 아니에요.
