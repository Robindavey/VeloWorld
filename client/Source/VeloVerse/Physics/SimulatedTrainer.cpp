#include "VeloVerse/Physics/SimulatedTrainer.h"

namespace VeloVerse::Physics {

SimulatedTrainer::SimulatedTrainer(float constantPowerW)
    : m_constantPowerW(constantPowerW) {}

bool SimulatedTrainer::Connect() {
    m_connected = true;
    return true;
}

void SimulatedTrainer::Disconnect() {
    m_connected = false;
}

bool SimulatedTrainer::IsConnected() const {
    return m_connected;
}

float SimulatedTrainer::GetPowerWatts() const {
    return m_connected ? m_constantPowerW : 0.0f;
}

float SimulatedTrainer::GetCadenceRPM() const {
    return m_connected ? 90.0f : 0.0f;
}

float SimulatedTrainer::GetSpeedKph() const {
    return 0.0f;
}

void SimulatedTrainer::SetResistanceForceN(float forceN) {
    m_lastResistanceN = forceN;
}

void SimulatedTrainer::SetGradientPercent(float gradient) {
    m_lastGradientPercent = gradient;
}

void SimulatedTrainer::SetERGTargetWatts(float targetWatts) {
    m_lastErgTargetW = targetWatts;
}

} // namespace VeloVerse::Physics

