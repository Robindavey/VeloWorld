#pragma once

#include <string>
#include <unordered_map>

namespace VeloWorld::Trainer {

struct CalibrationProfile {
    float resistanceScale{1.0f};
    float resistanceOffsetN{0.0f};
};

class TrainerCalibration {
public:
    bool LoadFromJsonFile(const std::string& path);

    CalibrationProfile GetProfileOrDefault(const std::string& deviceId) const;

private:
    std::unordered_map<std::string, CalibrationProfile> m_profiles;
};

} // namespace VeloWorld::Trainer

