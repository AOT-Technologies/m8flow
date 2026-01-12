# bootstrap.py
# Extension bootstrap code for M8Flow-specific patches.
# This module is imported by extensions/app.py before creating the app.
# Add any other extension-wide initialization code here.
# This file is part of the M8Flow extension to SpiffWorkflow Backend.

def bootstrap() -> None:
    from m8flow_backend.services.file_system_service_patch import apply as apply_file_system_service_patch
    apply_file_system_service_patch()

