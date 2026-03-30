#include "ANTPlusFECDriver.h"

namespace VeloWorld::Trainer {

ANTPlusFECDriver::ANTPlusFECDriver(std::string deviceId) : connected_(false), device_id(deviceId) {}

bool ANTPlusFECDriver::Connect() {
    // TODO: Implement ANT+ FE-C connection using libusb and ANT+ protocol
    // Requires ANT+ USB stick (e.g., Garmin ANT+ stick)
    // For now, stub
    connected_ = true; // Simulate connection
    return true;
}

void ANTPlusFECDriver::Disconnect() {
    // TODO: Implement disconnection
    connected_ = false;
}

bool ANTPlusFECDriver::IsConnected() const {
    return connected_;
}

float ANTPlusFECDriver::GetPowerWatts() const {
    // TODO: Read from ANT+ device
    return 0.0f; // Stub
}

float ANTPlusFECDriver::GetCadenceRPM() const {
    // TODO: Read from ANT+ device
    return 0.0f; // Stub
}

float ANTPlusFECDriver::GetSpeedKph() const {
    // TODO: Read from ANT+ device
    return 0.0f; // Stub
}

void ANTPlusFECDriver::SetResistanceForceN(float forceN) {
    // TODO: Send resistance command via ANT+
    (void)forceN; // Suppress unused parameter warning
}

void ANTPlusFECDriver::SetGradientPercent(float gradient) {
    // TODO: Send gradient command via ANT+
    (void)gradient; // Suppress unused parameter warning
}

void ANTPlusFECDriver::SetERGTargetWatts(float targetWatts) {
    // TODO: Send ERG target via ANT+
    (void)targetWatts; // Suppress unused parameter warning
}

} // namespace VeloWorld::Trainer