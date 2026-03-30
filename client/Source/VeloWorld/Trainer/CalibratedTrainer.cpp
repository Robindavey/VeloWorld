#include "CalibratedTrainer.h"

namespace VeloWorld::Trainer {

CalibratedTrainer::CalibratedTrainer(std::unique_ptr<VeloWorld::Physics::TrainerInterface> inner, CalibrationProfile cal)
    : m_inner(std::move(inner)), m_calibration(cal) {}

bool CalibratedTrainer::Connect() {
    return m_inner->Connect();
}

void CalibratedTrainer::Disconnect() {
    m_inner->Disconnect();
}

bool CalibratedTrainer::IsConnected() const {
    return m_inner->IsConnected();
}

float CalibratedTrainer::GetPowerWatts() const {
    return m_inner->GetPowerWatts();
}

float CalibratedTrainer::GetCadenceRPM() const {
    return m_inner->GetCadenceRPM();
}

float CalibratedTrainer::GetSpeedKph() const {
    return m_inner->GetSpeedKph();
}

void CalibratedTrainer::SetResistanceForceN(float forceN) {
    // Apply calibration: scale and offset
    float calibratedForce = forceN * m_calibration.resistanceScale + m_calibration.resistanceOffsetN;
    m_inner->SetResistanceForceN(calibratedForce);
}

void CalibratedTrainer::SetGradientPercent(float gradient) {
    // For gradient, perhaps no calibration, or apply if needed
    m_inner->SetGradientPercent(gradient);
}

void CalibratedTrainer::SetERGTargetWatts(float targetWatts) {
    // For ERG, perhaps no calibration
    m_inner->SetERGTargetWatts(targetWatts);
}

} // namespace VeloWorld::Trainer