#include <iostream>
#include <string>
#include <vector>
#include <memory>
#include <thread>
#include <chrono>
#include <cmath>

#include "VeloVerse/Trainer/TrainerManager.h"
#include "VeloVerse/Sensors/BLEHRMDriver.h"
#include "VeloVerse/Physics/RouteProfile.h"
#include "VeloVerse/Physics/PhysicsEngine.h"
#include "VeloVerse/Physics/SimulatedTrainer.h"

using namespace VeloVerse;

// Mock route data for demonstration
struct RouteSummary {
    double totalDistanceKm;
    double totalElevationM;
    double maxElevationM;
    double minElevationM;
    std::string name;
};

RouteSummary processFileToRoute(const std::string& filePath) {
    // TODO: Actually process .fit, .tcx, .gpx files
    // For now, mock based on file extension
    RouteSummary summary;
    summary.name = "Mock Route from " + filePath;

    if (filePath.find(".fit") != std::string::npos) {
        summary.totalDistanceKm = 25.5;
        summary.totalElevationM = 450.0;
        summary.maxElevationM = 1200.0;
        summary.minElevationM = 750.0;
    } else if (filePath.find(".tcx") != std::string::npos) {
        summary.totalDistanceKm = 18.2;
        summary.totalElevationM = 320.0;
        summary.maxElevationM = 800.0;
        summary.minElevationM = 480.0;
    } else if (filePath.find(".gpx") != std::string::npos) {
        summary.totalDistanceKm = 32.1;
        summary.totalElevationM = 680.0;
        summary.maxElevationM = 1500.0;
        summary.minElevationM = 820.0;
    } else {
        summary.totalDistanceKm = 20.0;
        summary.totalElevationM = 300.0;
        summary.maxElevationM = 1000.0;
        summary.minElevationM = 700.0;
    }

    return summary;
}

void displayRouteProfile(const RouteSummary& summary) {
    std::cout << "\n=== Route Profile ===" << std::endl;
    std::cout << "Name: " << summary.name << std::endl;
    std::cout << "Total Distance: " << summary.totalDistanceKm << " km" << std::endl;
    std::cout << "Total Elevation Gain: " << summary.totalElevationM << " m" << std::endl;
    std::cout << "Elevation Range: " << summary.minElevationM << "m - " << summary.maxElevationM << "m" << std::endl;

    // Simple ASCII elevation profile
    std::cout << "\nElevation Profile:" << std::endl;
    const int profileWidth = 50;
    double elevationRange = summary.maxElevationM - summary.minElevationM;
    for (int i = 0; i < 10; ++i) {
        double elevation = summary.minElevationM + (elevationRange * i / 9.0);
        int height = static_cast<int>((elevation - summary.minElevationM) / elevationRange * 20);
        std::cout << std::string(height, '|') << " " << static_cast<int>(elevation) << "m" << std::endl;
    }
}

void displayHUD(const Physics::PhysicsEngine& engine, int hr) {
    const auto& state = engine.GetState();
    std::cout << "\n=== HUD ===" << std::endl;
    std::cout << "Speed: " << state.velocityMs * 3.6 << " km/h" << std::endl;
    std::cout << "Distance: " << state.positionM / 1000.0 << " km" << std::endl;
    std::cout << "Power: " << state.powerW << " W" << std::endl;
    std::cout << "Heart Rate: " << hr << " BPM" << std::endl;
    std::cout << "Cadence: " << 90 << " RPM" << std::endl; // Mock cadence
    std::cout << "Gradient: " << state.gradientPercent << " %" << std::endl;
}

void sensorDiscoveryLoop(Trainer::TrainerManager& tm, Sensors::BLEHRMDriver& hrm, bool& running) {
    while (running) {
        std::cout << "\r🔍 Scanning for sensors..." << std::flush;
        std::this_thread::sleep_for(std::chrono::seconds(2));
        // In real implementation, this would continuously scan
    }
    std::cout << std::endl;
}

int main() {
    std::cout << "🚴 VeloVerse Cycling Simulator" << std::endl;
    std::cout << "================================" << std::endl;

    // Step 1: Load route from file
    std::string filePath;
    std::cout << "\nStep 1: Enter path to route file (.fit, .tcx, or .gpx): ";
    std::getline(std::cin, filePath);

    if (filePath.empty()) {
        std::cout << "No file provided. Exiting." << std::endl;
        return 0;
    }

    RouteSummary route = processFileToRoute(filePath);

    std::cout << "\n✅ Route loaded successfully!" << std::endl;
    std::cout << "Summary Stats:" << std::endl;
    std::cout << "- Distance: " << route.totalDistanceKm << " km" << std::endl;
    std::cout << "- Elevation Gain: " << route.totalElevationM << " m" << std::endl;

    // Step 2: Sensor discovery
    std::cout << "\nStep 2: Starting sensor discovery..." << std::endl;

    Trainer::TrainerManager tm;
    tm.LoadCalibrationDb("calibration.json");

    Sensors::BLEHRMDriver hrm;

    bool scanning = true;
    std::thread scanner(sensorDiscoveryLoop, std::ref(tm), std::ref(hrm), std::ref(scanning));

    // Attempt connections
    std::cout << "Attempting to connect to devices..." << std::endl;

    Trainer::TrainerSelection trainerSel{Trainer::ConnectionType::BLE_FTMS, "wahoo_kicker"};
    auto trainer = tm.CreateTrainer(trainerSel);
    bool trainerConnected = trainer && trainer->Connect();

    bool hrmConnected = hrm.Connect();

    scanning = false;
    scanner.join();

    std::cout << "\n📡 Sensor Status:" << std::endl;
    std::cout << (trainerConnected ? "✅ " : "❌ ") << "Smart Trainer: " << (trainerConnected ? "Connected" : "Not found") << std::endl;
    std::cout << (hrmConnected ? "✅ " : "❌ ") << "Heart Rate Monitor: " << (hrmConnected ? "Connected" : "Not found") << std::endl;

    // Step 3: Display route profile
    displayRouteProfile(route);

    // Step 4: Start simulation and show HUD
    std::cout << "\nStep 4: Starting simulation..." << std::endl;

    // Create mock route profile
    std::vector<Physics::RouteAttributes> routeData(1000); // 1km route with 1m samples
    for (size_t i = 0; i < routeData.size(); ++i) {
        routeData[i].gradientPercent = 2.0 * sin(i * 0.01); // Varying gradient
        routeData[i].elevationM = 800.0 + i * 0.2; // Rising elevation
        routeData[i].surfaceType = 1; // Asphalt
        routeData[i].cornerRadiusM = 100.0; // Straight
    }

    Physics::RouteProfile routeProfile;
    routeProfile.SetAttributesForTesting(routeData);

    Physics::RiderConfig config;
    config.systemMassKg = 75.0;
    config.tyreCrrModifier = 1.0;
    config.cdA = 0.32f;

    std::unique_ptr<Physics::TrainerInterface> simTrainer = std::make_unique<Physics::SimulatedTrainer>(200.0); // 200W constant power
    Physics::PhysicsEngine engine;
    engine.Initialise(routeProfile, config, simTrainer.get());

    std::cout << "\n🎯 Simulation running. Press Enter to update HUD, 'q' to quit." << std::endl;

    std::string input;
    while (true) {
        // Run simulation for 1 second
        for (int i = 0; i < 60; ++i) {
            engine.Tick(1.0f / 60.0f);
        }

        displayHUD(engine, hrmConnected ? hrm.GetHeartRateBPM() : 0);

        std::cout << "\nCommand (Enter to continue, 'q' to quit): ";
        std::getline(std::cin, input);
        if (input == "q" || input == "Q") {
            break;
        }
    }

    std::cout << "\n🏁 Simulation ended. Thanks for using VeloVerse!" << std::endl;
    return 0;
}