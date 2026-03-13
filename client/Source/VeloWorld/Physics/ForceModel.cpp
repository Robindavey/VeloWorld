#include "VeloWorld/Physics/ForceModel.h"

#include <algorithm>
#include <cmath>

namespace VeloWorld::Physics {

namespace {
constexpr float kG = 9.81f;
constexpr float kMinVelocity = 0.1f; // m/s to avoid divide-by-zero
} // namespace

static float GradientPercentToDeg(float gradientPercent) {
    const float thetaRad = std::atan(gradientPercent / 100.0f);
    return thetaRad * 180.0f / static_cast<float>(M_PI);
}

float ForceModel::ComputeGravityForce(float gradientDeg, float systemMassKg) {
    const float thetaRad = gradientDeg * static_cast<float>(M_PI) / 180.0f;
    return systemMassKg * kG * std::sin(thetaRad);
}

float ForceModel::ComputeRollingResistance(float crr, float systemMassKg, float gradientDeg) {
    const float thetaRad = gradientDeg * static_cast<float>(M_PI) / 180.0f;
    return crr * systemMassKg * kG * std::cos(thetaRad);
}

float ForceModel::ComputeAerodynamicDrag(float cdA, float velocityMs, float airDensity, float windComponentMs) {
    const float vAir = velocityMs + windComponentMs;
    if (vAir <= 0.0f) {
        return 0.0f;
    }
    return 0.5f * airDensity * cdA * vAir * vAir;
}

float ForceModel::ComputeAirDensity(float altitudeM, float temperatureC) {
    // Altitude component: rho = 1.225 * exp(-altitude / 8500)
    const float rhoAlt = 1.225f * std::exp(-altitudeM / 8500.0f);
    // Temperature adjustment: rho *= 273.15 / (273.15 + T)
    const float tempFactor = 273.15f / (273.15f + temperatureC);
    return rhoAlt * tempFactor;
}

float ForceModel::SurfaceCrr(int32_t surfaceType) {
    // Surface parameter table from physics spec (subset).
    // Mapping is internal to MVP; pipeline should align numeric IDs later.
    switch (surfaceType) {
    case 0: // Race asphalt
        return 0.003f;
    case 1: // Standard tarmac
        return 0.005f;
    case 2: // Rough tarmac
        return 0.007f;
    case 3: // Wet tarmac
        return 0.007f;
    case 4: // Concrete
        return 0.006f;
    case 5: // Cobblestone
        return 0.015f;
    case 6: // Compacted gravel
        return 0.010f;
    case 7: // Loose gravel
        return 0.022f;
    default:
        return 0.005f;
    }
}

float ForceModel::SurfaceMuLateralDry(int32_t surfaceType) {
    switch (surfaceType) {
    case 0: // Race asphalt
        return 0.70f;
    case 1: // Standard tarmac
        return 0.65f;
    case 2: // Rough tarmac
        return 0.62f;
    case 4: // Concrete
        return 0.63f;
    case 5: // Cobblestone
        return 0.50f;
    case 6: // Compacted gravel
        return 0.45f;
    case 7: // Loose gravel
        return 0.42f;
    default:
        return 0.65f;
    }
}

float ForceModel::SurfaceMuBrakeDry(int32_t surfaceType) {
    // Braking friction coefficients (dry) from spec.
    switch (surfaceType) {
    case 0: // Race asphalt (treat like smooth asphalt)
        return 0.75f;
    case 1: // Standard tarmac
        return 0.70f;
    case 2: // Rough tarmac
        return 0.68f;
    case 4: // Concrete
        return 0.68f;
    case 5: // Cobblestone
        return 0.60f;
    case 6: // Compacted gravel
        return 0.55f;
    case 7: // Loose gravel (use gravel)
        return 0.55f;
    default:
        return 0.70f;
    }
}

float ForceModel::ComputeTotalForce(const RouteAttributes& route,
                                    const RiderConfig& config,
                                    float velocityMs,
                                    float windComponentMs,
                                    float temperatureC) {
    const float gradientDeg = GradientPercentToDeg(route.gradientPercent);
    const float gravity = ComputeGravityForce(gradientDeg, config.systemMassKg);
    const float crr = SurfaceCrr(route.surfaceType) * config.tyreCrrModifier;
    const float rolling = ComputeRollingResistance(crr, config.systemMassKg, gradientDeg);
    const float airDensity = ComputeAirDensity(route.elevationM, temperatureC);
    const float aero = ComputeAerodynamicDrag(config.cdA, velocityMs, airDensity, windComponentMs);
    return gravity + rolling + aero;
}

float ForceModel::SolveVelocity(float powerW,
                                float totalForceN,
                                float systemMassKg,
                                float prevVelocityMs,
                                float dtS) {
    float v = std::max(prevVelocityMs, kMinVelocity);
    const float resistivePower = totalForceN * v;
    const float netForce = (powerW - resistivePower) / std::max(v, kMinVelocity);
    const float acceleration = netForce / systemMassKg;
    float newV = prevVelocityMs + acceleration * dtS;
    if (newV < 0.0f) {
        newV = 0.0f;
    }
    return newV;
}

} // namespace VeloWorld::Physics

