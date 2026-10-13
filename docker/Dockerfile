# Official ROS1 baseline (ROS Noetic / Ubuntu 20.04 image, runs on any x86_64 host
# with Docker, including Ubuntu 22.04 and Windows + Docker Desktop).
#
# Prior to building, fetch the pinned sources referenced by the COPY steps:
#     python scripts/fetch_pinned_sources.py
# Optionally seed the apt cache (offline/CN friendly):
#     python scripts/prefetch_debs.py
#
# Build from the repository root:
#     docker build -f docker/Dockerfile -t fastlivo2:noetic-local .
FROM ros:noetic-ros-base-focal@sha256:72b8bc59035dc0a5b8e07aae28c16caa84192971d72d207c72ed734fb1d5e97d
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ARG DEBIAN_FRONTEND=noninteractive
ARG BUILD_JOBS=4
ARG VIKIT_COMMIT=6c886c8e5d83997806e00294826d528cea3581dd
ARG APT_MIRROR=mirrors.aliyun.com
RUN --mount=type=cache,target=/var/cache/apt,id=fastlivo-noetic-apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,id=fastlivo-noetic-lists,sharing=locked \
    --mount=type=bind,source=downloads/noetic_debs,target=/seed-debs \
    rm -f /etc/apt/apt.conf.d/docker-clean \
    && mkdir -p /var/cache/apt/archives \
    && if compgen -G "/seed-debs/*.deb" > /dev/null; then \
         for deb in /seed-debs/*.deb; do \
           name=$(dpkg-deb --showformat='${Package}_${Version}_${Architecture}.deb' -W "$deb"); \
           cp -n "$deb" "/var/cache/apt/archives/${name//:/%3a}"; \
         done; \
       else \
         echo "no seeded .deb files found; using network only"; \
       fi \
    && sed -i -e "s|http://archive.ubuntu.com/ubuntu|http://${APT_MIRROR}/ubuntu|g" \
              -e "s|http://security.ubuntu.com/ubuntu|http://${APT_MIRROR}/ubuntu|g" /etc/apt/sources.list \
    && apt-get -o Acquire::Retries=3 -o Acquire::http::Timeout=30 update \
    && apt-get -o Acquire::Retries=3 -o Acquire::http::Timeout=30 install -y --no-install-recommends \
    build-essential cmake git ca-certificates python3-yaml python3-pip \
    libeigen3-dev libopencv-dev libpcl-dev libboost-thread-dev \
    ros-noetic-pcl-ros ros-noetic-eigen-conversions ros-noetic-cv-bridge \
    ros-noetic-image-transport ros-noetic-compressed-image-transport \
    ros-noetic-tf ros-noetic-rviz ros-noetic-image-proc
COPY upstream/Sophus_pinned/ /opt/Sophus/
# C++ complex accessors on newer GCC require setters for this old Sophus version.
RUN python3 - <<'PY'
from pathlib import Path
p = Path('/opt/Sophus/sophus/so2.cpp')
s = p.read_text()
s = s.replace('unit_complex_.real() = 1.;', 'unit_complex_.real(1.);')
s = s.replace('unit_complex_.imag() = 0.;', 'unit_complex_.imag(0.);')
p.write_text(s)
PY
RUN cmake -S /opt/Sophus -B /opt/Sophus/build \
    && cmake --build /opt/Sophus/build -j${BUILD_JOBS} \
    && cmake --install /opt/Sophus/build && ldconfig
COPY upstream/rpg_vikit_pinned/ /opt/fastlivo_ws/src/rpg_vikit/
COPY upstream/FAST-LIVO2/ /opt/fastlivo_ws/src/FAST-LIVO2/
RUN source /opt/ros/noetic/setup.bash \
    && sed -i 's/-march=native/-march=x86-64/g' /opt/fastlivo_ws/src/FAST-LIVO2/CMakeLists.txt /opt/fastlivo_ws/src/rpg_vikit/vikit_common/CMakeLists.txt \
    && cd /opt/fastlivo_ws && catkin_make -j${BUILD_JOBS} -l${BUILD_JOBS} \
    && mkdir -p src/FAST-LIVO2/Log/result src/FAST-LIVO2/Log/pcd
COPY scripts/container_entrypoint.sh /usr/local/bin/fastlivo-entrypoint
RUN chmod +x /usr/local/bin/fastlivo-entrypoint
WORKDIR /opt/fastlivo_ws
ENTRYPOINT ["/usr/local/bin/fastlivo-entrypoint"]
CMD ["bash"]
