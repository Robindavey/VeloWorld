#pragma once

#include "VeloVerse/Physics/TrainerInterface.h"
#include "VeloVerse/Trainer/TrainerCalibration.h"

#include <memory>
#include <string>

namespace VeloVerse::Trainer {

enum class ConnectionType {
    None = 0,
    BLE_FTMS,
    ANT_FEC,
};

struct TrainerSelection {
    ConnectionType type{ConnectionType::None};
    std::string deviceId;
};

class TrainerManager {
public:
    TrainerManager();

    bool LoadCalibrationDb(const std::string& path);

    // For now: create a placeholder driver that implements the interface.
    // Deliverable 5 will replace these with real BLE/ANT implementations.
    std::unique_ptr<VeloVerse::Physics::TrainerInterface> CreateTrainer(const TrainerSelection& selection) const;

    CalibrationProfile GetCalibrationForDevice(const std::string& deviceId) const;

private:
    TrainerCalibration m_calibration;
};

} // namespace VeloVerse::Trainer

