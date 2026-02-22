"""
Schema versions for artifact contracts. Gatekeeper requires these for candidate/accepted.
Prevents silent schema drift from undermining auditability.
"""

from __future__ import annotations

# Validation bundle (meta): required in bundle.meta for candidate/accepted
VALIDATION_BUNDLE_SCHEMA_VERSION = 1

# RC summary (rc_summary.json / rc_summary dict): required when rc_summary is used for promotion
RC_SUMMARY_SCHEMA_VERSION = 1

# Calibration harness outputs: for persisted calibration results
CALIBRATION_HARNESS_SCHEMA_VERSION = 1
