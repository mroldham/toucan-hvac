from app import app, db, MonitoringDevice, MonitoringAlert, MonitoringNotificationSetting
from datetime import datetime, timedelta

OFFLINE_MINUTES = 20

with app.app_context():
    cutoff = datetime.utcnow() - timedelta(minutes=OFFLINE_MINUTES)
    setting = MonitoringNotificationSetting.query.first()

    devices = MonitoringDevice.query.all()
    created = 0

    for device in devices:
        if not device.last_seen or device.last_seen < cutoff:
            existing = MonitoringAlert.query.filter_by(
                device_id=device.id,
                alert_type="device_offline",
                resolved=False
            ).first()

            if existing:
                continue

            msg = f"{device.device_name} has not checked in for more than {OFFLINE_MINUTES} minutes."

            alert = MonitoringAlert(
                device_id=device.id,
                alert_type="device_offline",
                severity="warning",
                message=msg
            )

            if setting:
                alert.send_sms = bool(setting.sms_enabled)
                alert.sms_phone_number = setting.sms_phone_number
                alert.send_email = bool(setting.email_enabled)
                alert.email_address = setting.email_address

            db.session.add(alert)
            created += 1

    db.session.commit()
    print(f"Offline alerts created: {created}")
