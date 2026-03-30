#pragma once

#include "VeloWorld/Physics/TrainerInterface.h"
#include <string>

namespace VeloWorld::Trainer {

class BLEFTMSDriver : public VeloWorld::Physics::TrainerInterface {
public:
    explicit BLEFTMSDriver(std::string deviceId);
    ~BLEFTMSDriver() override = default;

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
    std::string device_address;
};

} // namespace VeloWorld::Trainer