#pragma once

#include <cstdint>

namespace VeloVerse::Physics {

struct RouteAttributes {
    float gradientPercent{};
    float cornerRadiusM{};
    float bankingDeg{};
    int32_t surfaceType{};
    float elevationM{};
};

struct RiderConfig {
    float systemMassKg{}; // rider + bike
    float tyreCrrModifier{1.0f}; // multiply surface Crr (e.g. 0.85 race tubeless)
    float cdA{};          // aerodynamic CdA
};

class ForceModel {
public:
    static float ComputeGravityForce(float gradientDeg, float systemMassKg);
    static float ComputeRollingResistance(float crr, float systemMassKg, float gradientDeg);
    static float ComputeAerodynamicDrag(float cdA, float velocityMs, float airDensity, float windComponentMs);
    static float ComputeAirDensity(float altitudeM, float temperatureC);

    static float SurfaceCrr(int32_t surfaceType);
    static float SurfaceMuLateralDry(int32_t surfaceType);
    static float SurfaceMuBrakeDry(int32_t surfaceType);

    static float ComputeTotalForce(const RouteAttributes& route,
                                   const RiderConfig& config,
                                   float velocityMs,
                                   float windComponentMs,
                                   float temperatureC);

    static float SolveVelocity(float powerW,
                               float totalForceN,
                               float systemMassKg,
                               float prevVelocityMs,
                               float dtS);
};

} // namespace VeloVerse::Physics

