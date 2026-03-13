#pragma once

namespace VeloWorld::Physics {

class TrainerInterface {
public:
    virtual ~TrainerInterface() = default;

    virtual bool Connect() = 0;
    virtual void Disconnect() = 0;
    virtual bool IsConnected() const = 0;

    virtual float GetPowerWatts() const = 0;
    virtual float GetCadenceRPM() const = 0;
    virtual float GetSpeedKph() const = 0;

    virtual void SetResistanceForceN(float forceN) = 0;
    virtual void SetGradientPercent(float gradient) = 0;
    virtual void SetERGTargetWatts(float targetWatts) = 0;
};

} // namespace VeloWorld::Physics

