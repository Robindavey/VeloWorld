#include "VeloWorld/Physics/RouteProfile.h"

#include <algorithm>
#include <fstream>
#include <nlohmann/json.hpp>

namespace VeloWorld::Physics {

using nlohmann::json;

bool RouteProfile::LoadFromJsonFile(const std::string& path) {
    std::ifstream in(path);
    if (!in.is_open()) {
        return false;
    }
    json j;
    in >> j;
    if (!j.is_array()) {
        return false;
    }
    m_attributes.clear();
    m_attributes.reserve(j.size());
    for (const auto& item : j) {
        RouteAttributes attrs{};
        attrs.gradientPercent = item.value("gradient_percent", 0.0f);
        attrs.cornerRadiusM = item.value("corner_radius_m", 0.0f);
        attrs.bankingDeg = item.value("banking_deg", 0.0f);
        attrs.surfaceType = item.value("surface_type", 0);
        attrs.elevationM = item.value("elevation_m", 0.0f);
        m_attributes.push_back(attrs);
    }
    return !m_attributes.empty();
}

RouteAttributes RouteProfile::GetAttributesAtPosition(float positionM) const {
    if (m_attributes.empty()) {
        return {};
    }
    if (positionM <= 0.0f) {
        return m_attributes.front();
    }
    const float maxIndex = static_cast<float>(m_attributes.size() - 1);
    float idx = std::clamp(positionM, 0.0f, maxIndex);
    const size_t i0 = static_cast<size_t>(idx);
    const size_t i1 = std::min(i0 + 1, m_attributes.size() - 1);
    const float t = idx - static_cast<float>(i0);

    const auto& a0 = m_attributes[i0];
    const auto& a1 = m_attributes[i1];
    RouteAttributes out{};
    out.gradientPercent = a0.gradientPercent + (a1.gradientPercent - a0.gradientPercent) * t;
    out.cornerRadiusM = a0.cornerRadiusM + (a1.cornerRadiusM - a0.cornerRadiusM) * t;
    out.bankingDeg = a0.bankingDeg + (a1.bankingDeg - a0.bankingDeg) * t;
    out.surfaceType = (t < 0.5f) ? a0.surfaceType : a1.surfaceType;
    out.elevationM = a0.elevationM + (a1.elevationM - a0.elevationM) * t;
    return out;
}

} // namespace VeloWorld::Physics

