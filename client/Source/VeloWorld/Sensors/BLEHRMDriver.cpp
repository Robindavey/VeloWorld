#include "BLEHRMDriver.h"

namespace VeloWorld::Sensors {

BLEHRMDriver::BLEHRMDriver() : connected_(false), last_hr_(0) {}

bool BLEHRMDriver::Connect() {
    // TODO: Implement BLE HRM connection using BlueZ DBus
    // Scan for HRM service UUID: 0x180D
    // Connect and subscribe to heart rate measurement characteristic
    connected_ = true; // Stub
    return true;
}

void BLEHRMDriver::Disconnect() {
    // TODO: Disconnect
    connected_ = false;
}

bool BLEHRMDriver::IsConnected() const {
    return connected_;
}

int BLEHRMDriver::GetHeartRateBPM() const {
    // TODO: Read from BLE device
    return last_hr_; // Stub, return last read value
}

} // namespace VeloWorld::Sensors