#pragma once

#include "VeloVerse/Physics/TrainerInterface.h"
#include "TrainerCalibration.h"

#include <memory>

namespace VeloVerse::Trainer {

class CalibratedTrainer : public VeloVerse::Physics::TrainerInterface {
public:
    CalibratedTrainer(std::unique_ptr<VeloVerse::Physics::TrainerInterface> inner, CalibrationProfile cal);

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
    std::unique_ptr<VeloVerse::Physics::TrainerInterface> m_inner;
    CalibrationProfile m_calibration;
};

} // namespace VeloVerse::Trainer