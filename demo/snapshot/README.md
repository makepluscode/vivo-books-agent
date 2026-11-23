# VIVO BOOKS 심사용 데모 결과

[개정 리더](reader.html)에서 원고와 저자 검토용 미리보기를 번갈아 볼 수 있어요. 리더와 연결된 파일을 같은 폴더에 두고 브라우저에서 열어요.

- [PR 초안](pr.md), [독자 정오표](ERRATA.md), [개정 이력](REVISIONS.md)은 기록을 재생해 로컬 Git 브랜치에서 만든 결과예요. PR 초안이 말하는 `dist/`의 개정 EPUB은 책 저장소 브랜치 안의 경로이고, 이 폴더에서는 [preview.epub](preview.epub)이 같은 파일이에요.
- [원본 EPUB](original.epub)과 [개정 EPUB](preview.epub), [원고 변경 비교](manuscript.diff), [검증 기록](revision.json)을 함께 확인할 수 있어요.
- [자동 테스트 실행 기록](tests.txt)에서 92개 테스트 결과를 볼 수 있어요.
- [문제 정의와 41% 측정 범위](../../docs/PROBLEM.md), [장 점검 평가 원자료](../../experiments/drift-agent/inspect-results-2026-11-22.md), [이전 개정 실험](../../docs/AGENT_EXPERIMENTS.md)이에요.

## 이 실행에서 확인한 것

- 기록된 PyPI 버전은 LangChain 1.5.2와 langchain-core 1.8.4예요. 실행 검증은 Python 3.14와 LangChain 1.5.0, langchain-core 1.8.1에서 했어요.
- 공개 저장소의 실제 개정 PR을 만든 실행의 Liner 응답 20건(Router 13건, Search 7건)을 재생하고, 수정된 예제를 격리 환경에서 다시 실행했어요. 설치 가능 여부는 pip dry-run으로 확인했어요.
- 1장에는 설치 안내와 API 설명을, 4·7장에는 예제 코드와 옆의 설명, 장별 예제 파일을 고쳤어요. 3장 원고와 EPUB 장 파일은 각각 해시가 같아요. 1장의 테스트 모델 설명 한 곳은 공식 근거가 없어 원문을 유지했고, 예제 저장소 위치를 알리는 19행은 책 자체 안내라 조사 대상에서 뺐어요(`book.json`의 `local_prose_lines`).
- 4장은 `prompt | 모델 | 파서` 체인을 실제로 거치는지와, 미리 알 수 없는 숨은 질문의 출력이 원본 템플릿으로 계산한 값과 정확히 같은지 확인했어요. 7장은 도구 응답을 바꿨을 때 최종 답이 달라지는지, 처음 보는 도시에서도 도구 메시지가 아닌 에이전트의 최종 AI 답을 돌려주는지 확인했어요. 기록의 `tool_result_observation`에서 실제 출력을 볼 수 있어요.
- 같은 개정안이 공개 가상 기술서 저장소의 실제 PR [vivo-books-sample-book#2](https://github.com/makepluscode/vivo-books-sample-book/pull/2)로 올라가 있어요. 이 폴더의 결과는 그 실행을 재생한 것으로, 원고·예제 파일·EPUB 장 해시가 PR과 같아요.

직접 실행하는 방법은 [저장소 README](../../README.md#바로-보기)에 있어요.
