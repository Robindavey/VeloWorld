#pragma once

#include "VeloVerse/Physics/TrainerInterface.h"

namespace VeloVerse::Physics {

class SimulatedTrainer : public TrainerInterface {
public:
    explicit SimulatedTrainer(float constantPowerW = 200.0f);

    bool Connect() override;
    void Disconnect() override;
    bool IsConnected() const override;

    float GetPowerWatts() const override;
    float GetCadenceRPM() const override;
    float GetSpeedKph() const override;

    void SetResistanceForceN(float forceN) override;
    void SetGradientPercent(float gradient) override;
    void SetERGTargetWatts(float targetWatts) override;

    float GetLastResistanceCommandN() const { return m_lastResistanceN; }
    float GetLastGradientCommandPercent() const { return m_lastGradientPercent; }
    float GetLastERGTargetWatts() const { return m_lastErgTargetW; }

private:
    bool m_connected{false};
    float m_constantPowerW{200.0f};
    float m_lastResistanceN{0.0f};
    float m_lastGradientPercent{0.0f};
    float m_lastErgTargetW{0.0f};
};

} // namespace VeloVerse::Physics

