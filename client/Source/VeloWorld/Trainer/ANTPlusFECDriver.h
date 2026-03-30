#pragma once

#include "VeloWorld/Physics/TrainerInterface.h"
#include <string>

namespace VeloWorld::Trainer {

class ANTPlusFECDriver : public VeloWorld::Physics::TrainerInterface {
public:
    explicit ANTPlusFECDriver(std::string deviceId);
    ~ANTPlusFECDriver() override = default;

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
    bool connected_;
    std::string device_id;
};

} // namespace VeloWorld::Trainer