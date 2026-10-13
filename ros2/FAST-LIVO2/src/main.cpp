#include "LIVMapper.h"
#include <csignal>

volatile std::sig_atomic_t g_fastlivo_stop = 0;

static void request_stop(int)
{
  g_fastlivo_stop = 1;
}

int main(int argc, char **argv)
{
  rclcpp::init(argc, argv, rclcpp::InitOptions(), rclcpp::SignalHandlerOptions::None);
  std::signal(SIGINT, request_stop);
  std::signal(SIGTERM, request_stop);
  {
    // Keep the ROS context valid while the node, subscriptions and timers die.
    auto nh = std::make_shared<rclcpp::Node>("laserMapping");
    image_transport::ImageTransport it_(nh);
    LIVMapper mapper(nh, "laserMapping");
    mapper.initializeSubscribersAndPublishers(nh, it_);
    mapper.run(nh);
  }
  rclcpp::shutdown();
  return 0;
}
