#include "VeloWorld/Trainer/TrainerManager.h"
#include "VeloWorld/Trainer/BLEFTMSDriver.h"
#include "VeloWorld/Trainer/ANTPlusFECDriver.h"
#include "VeloWorld/Trainer/CalibratedTrainer.h"

#include <stdexcept>

namespace VeloWorld::Trainer {

TrainerManager::TrainerManager() = default;

bool TrainerManager::LoadCalibrationDb(const std::string& path) {
    return m_calibration.LoadFromJsonFile(path);
}

std::unique_ptr<VeloWorld::Physics::TrainerInterface> TrainerManager::CreateTrainer(const TrainerSelection& selection) const {
    std::unique_ptr<VeloWorld::Physics::TrainerInterface> driver;
    switch (selection.type) {
    case ConnectionType::BLE_FTMS:
        driver = std::make_unique<BLEFTMSDriver>(selection.deviceId);
        break;
    case ConnectionType::ANT_FEC:
        driver = std::make_unique<ANTPlusFECDriver>(selection.deviceId);
        break;
    case ConnectionType::None:
    default:
        return nullptr;
    }
    // Wrap with calibration
    auto cal = GetCalibrationForDevice(selection.deviceId);
    return std::make_unique<CalibratedTrainer>(std::move(driver), cal);
}

CalibrationProfile TrainerManager::GetCalibrationForDevice(const std::string& deviceId) const {
    return m_calibration.GetProfileOrDefault(deviceId);
}

} // namespace VeloWorld::Trainer

