"""The web layer: receives uploads, validates them, calls pipeline/, returns typed JSON.

Rule of this package: NO newspaper logic here. If you are tempted to put OCR, layout or text
cleaning in api/, it belongs in pipeline/ instead.

    settings.py   configuration (env vars)           errors.py   one error shape for every failure
    schemas.py    the JSON contract (Pydantic)       uploads.py  safe handling of an uploaded file
    health.py     "is the machine able to work?"     main.py     the routes, nothing else
"""
