#include "VeloVerse/Trainer/TrainerCalibration.h"

#include <fstream>
#include <nlohmann/json.hpp>

namespace VeloVerse::Trainer {

using nlohmann::json;

bool TrainerCalibration::LoadFromJsonFile(const std::string& path) {
    std::ifstream in(path);
    if (!in.is_open()) {
        return false;
    }
    json j;
    in >> j;
    if (!j.is_object()) {
        return false;
    }

    m_profiles.clear();
    for (auto it = j.begin(); it != j.end(); ++it) {
        const std::string deviceId = it.key();
        const auto& v = it.value();
        CalibrationProfile p{};
        p.resistanceScale = v.value("resistance_scale", 1.0f);
        p.resistanceOffsetN = v.value("resistance_offset_n", 0.0f);
        m_profiles.emplace(deviceId, p);
    }

    return true;
}

CalibrationProfile TrainerCalibration::GetProfileOrDefault(const std::string& deviceId) const {
    auto it = m_profiles.find(deviceId);
    if (it == m_profiles.end()) {
        return {};
    }
    return it->second;
}

} // namespace VeloVerse::Trainer

