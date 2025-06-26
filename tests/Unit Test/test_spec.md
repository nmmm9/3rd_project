# 테스트 명세 문서

| 테스트 파일                | 테스트 함수                | 목적/설명                              | 입력/조건                | 기대 결과                |
|---------------------------|---------------------------|----------------------------------------|--------------------------|--------------------------|
| test_app.py               | test_app_import           | app 모듈이 정상적으로 import되는지 확인 | -                        | import 성공              |
| test_chat_handler.py      | test_handle_chat          | handle_chat 함수의 정상 동작 검증       | mock 세션/메시지 입력    | dict, 'answer' 포함       |
| test_chat_memory.py       | test_module_import        | chat_memory 모듈 import 확인            | -                        | import 성공              |
| test_db.py                | test_create_and_get_user  | 사용자 생성/조회 기능 검증              | 테스트용 유저 정보 입력  | 생성/조회 성공            |
| test_git_modifier.py      | test_module_import        | git_modifier 모듈 import 확인           | -                        | import 성공              |
| test_github_analyzer.py   | test_module_import        | github_analyzer 모듈 import 확인        | -                        | import 성공              | 