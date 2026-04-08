#pragma once

#include "VeloVerse/Sensors/HRMInterface.h"

namespace VeloVerse::Sensors {

class BLEHRMDriver : public HRMInterface {
public:
    BLEHRMDriver();
    ~BLEHRMDriver() override = default;

    bool Connect() override;
    void Disconnect() override;
    bool IsConnected() const override;

    int GetHeartRateBPM() const override;

private:
    bool connected_;
    int last_hr_;
};

} // namespace VeloVerse::Sensors