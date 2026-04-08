#include "VeloVerse/Physics/PhysicsEngine.h"

#include <algorithm>
#include <cmath>

namespace VeloVerse::Physics {

void PhysicsEngine::Initialise(const RouteProfile& route,
                               const RiderConfig& config,
                               TrainerInterface* trainer) {
    m_route = route;
    m_config = config;
    m_trainer = trainer;
    m_state = {};
    if (m_trainer && !m_trainer->IsConnected()) {
        m_trainer->Connect();
    }
}

void PhysicsEngine::Tick(float deltaTimeS) {
    if (!m_trainer) {
        return;
    }

    ReadTrainerData();

    const auto attrs = m_route.GetAttributesAtPosition(m_state.positionM);
    const float windComponentMs = 0.0f;
    const float temperatureC = 15.0f;

    const float totalForce = ForceModel::ComputeTotalForce(
        attrs, m_config, m_state.velocityMs, windComponentMs, temperatureC);

    float newVelocity = ForceModel::SolveVelocity(
        m_state.powerW, totalForce, m_config.systemMassKg, m_state.velocityMs, deltaTimeS);

    m_state.gradientPercent = attrs.gradientPercent;
    newVelocity = ApplyCornerBrakingIfNeeded(newVelocity, deltaTimeS);
    m_state.velocityMs = newVelocity;

    AdvancePosition(newVelocity, deltaTimeS);
    SendTrainerResistance(totalForce);
}

void PhysicsEngine::ReadTrainerData() {
    if (!m_trainer) {
        return;
    }
    m_state.powerW = m_trainer->GetPowerWatts();
}

void PhysicsEngine::SendTrainerResistance(float totalForceN) {
    if (!m_trainer) {
        return;
    }
    m_trainer->SetResistanceForceN(totalForceN);

    const float g = 9.81f;
    const float ratio = std::clamp(totalForceN / (m_config.systemMassKg * g), -1.0f, 1.0f);
    const float thetaRad = std::asin(ratio);
    const float gradientPercent = std::tan(thetaRad) * 100.0f;
    m_trainer->SetGradientPercent(gradientPercent);
}

void PhysicsEngine::AdvancePosition(float velocityMs, float dtS) {
    m_state.positionM += velocityMs * dtS;
}

float PhysicsEngine::ApplyCornerBrakingIfNeeded(float candidateVelocityMs, float dtS) {
    // Very simple corner speed management:
    // - Look ahead a short distance for an upcoming corner attribute.
    // - If safe corner speed is lower than current, brake toward it using mu_brake.
    constexpr float kLookaheadM = 15.0f;
    const auto upcoming = m_route.GetAttributesAtPosition(m_state.positionM + kLookaheadM);
    if (upcoming.cornerRadiusM <= 0.0f) {
        return candidateVelocityMs;
    }

    const float muLat = ForceModel::SurfaceMuLateralDry(upcoming.surfaceType);
    const float vMaxCorner = std::sqrt(std::max(0.0f, muLat * 9.81f * upcoming.cornerRadiusM));

    if (candidateVelocityMs <= vMaxCorner) {
        return candidateVelocityMs;
    }

    const float muBrake = ForceModel::SurfaceMuBrakeDry(upcoming.surfaceType);
    const float decel = muBrake * 9.81f; // simplified; ignores gradient cos(theta)
    const float braked = candidateVelocityMs - decel * dtS;
    return std::max(vMaxCorner, braked);
}

} // namespace VeloVerse::Physics

