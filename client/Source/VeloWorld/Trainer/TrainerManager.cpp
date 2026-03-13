#include "VeloWorld/Trainer/TrainerManager.h"

#include <stdexcept>

namespace VeloWorld::Trainer {

namespace {
class UnsupportedTrainer final : public VeloWorld::Physics::TrainerInterface {
public:
    explicit UnsupportedTrainer(std::string deviceId)
        : m_deviceId(std::move(deviceId)) {}

    bool Connect() override { return false; }
    void Disconnect() override {}
    bool IsConnected() const override { return false; }

    float GetPowerWatts() const override { return 0.0f; }
    float GetCadenceRPM() const override { return 0.0f; }
    float GetSpeedKph() const override { return 0.0f; }

    void SetResistanceForceN(float) override {}
    void SetGradientPercent(float) override {}
    void SetERGTargetWatts(float) override {}

private:
    std::string m_deviceId;
};
} // namespace

TrainerManager::TrainerManager() = default;

bool TrainerManager::LoadCalibrationDb(const std::string& path) {
    return m_calibration.LoadFromJsonFile(path);
}

std::unique_ptr<VeloWorld::Physics::TrainerInterface> TrainerManager::CreateTrainer(const TrainerSelection& selection) const {
    switch (selection.type) {
    case ConnectionType::BLE_FTMS:
    case ConnectionType::ANT_FEC:
        // Real implementations added in Deliverable 5.
        return std::make_unique<UnsupportedTrainer>(selection.deviceId);
    case ConnectionType::None:
    default:
        return nullptr;
    }
}

CalibrationProfile TrainerManager::GetCalibrationForDevice(const std::string& deviceId) const {
    return m_calibration.GetProfileOrDefault(deviceId);
}

} // namespace VeloWorld::Trainer

