#pragma once

#include "VeloWorld/Physics/ForceModel.h"
#include "VeloWorld/Physics/RouteProfile.h"
#include "VeloWorld/Physics/TrainerInterface.h"

namespace VeloWorld::Physics {

struct SimulationState {
    float positionM{};
    float velocityMs{};
    float powerW{};
    float gradientPercent{};
};

class PhysicsEngine {
public:
    PhysicsEngine() = default;

    void Initialise(const RouteProfile& route,
                    const RiderConfig& config,
                    TrainerInterface* trainer);

    void Tick(float deltaTimeS);

    SimulationState GetState() const { return m_state; }

private:
    void ReadTrainerData();
    void SendTrainerResistance(float totalForceN);
    void AdvancePosition(float velocityMs, float dtS);
    float ApplyCornerBrakingIfNeeded(float candidateVelocityMs, float dtS);

    RouteProfile m_route;
    RiderConfig m_config{};
    TrainerInterface* m_trainer{nullptr};
    SimulationState m_state{};
};

} // namespace VeloWorld::Physics

