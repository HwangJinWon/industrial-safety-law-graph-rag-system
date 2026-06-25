Frontend reference cleanup note

The following folders are excluded from source audit and team sharing review:

- dist/

Reason:
- dist/ is a generated build artifact.
- Removal was attempted, but Windows denied deletion for files inside this folder.
- Source audit must ignore this folder.

Folders that were not present during cleanup:
- node_modules/
- build/
- .vite/
- .cache/
- coverage/

Do not treat generated build/cache/dependency folders as source of truth.
