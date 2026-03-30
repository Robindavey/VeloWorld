#pragma once

#include "VeloWorld/Physics/TrainerInterface.h"
#include "TrainerCalibration.h"

#include <memory>

namespace VeloWorld::Trainer {

class CalibratedTrainer : public VeloWorld::Physics::TrainerInterface {
public:
    CalibratedTrainer(std::unique_ptr<VeloWorld::Physics::TrainerInterface> inner, CalibrationProfile cal);

    bool Connect() override;
    void Disconnect() override;
    bool IsConnected() const override;

    float GetPowerWatts() const override;
    float GetCadenceRPM() const override;
    float GetSpeedKph() const override;

    void SetResistanceForceN(float forceN) override;
    void SetGradientPercent(float gradient) override;
    void SetERGTargetWatts(float targetWatts) override;

private:
    std::unique_ptr<VeloWorld::Physics::TrainerInterface> m_inner;
    CalibrationProfile m_calibration;
};

} // namespace VeloWorld::Trainer