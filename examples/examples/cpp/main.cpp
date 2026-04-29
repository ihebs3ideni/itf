/********************************************************************************
 * Copyright (c) 2026 Contributors to the Eclipse Foundation
 *
 * See the NOTICE file(s) distributed with this work for additional
 * information regarding copyright ownership.
 *
 * This program and the accompanying materials are made available under the
 * terms of the Apache License Version 2.0 which is available at
 * https://www.apache.org/licenses/LICENSE-2.0
 *
 * SPDX-License-Identifier: Apache-2.0
 ********************************************************************************/
#include <cstring>
#include <iostream>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>

/**
 * Send a UDP datagram to localhost:<port>.
 * Returns 0 on success, -1 on failure.
 * UDP is connectionless — the packet is sent even without a listener.
 */
static int send_udp_message(int port, const char *message)
{
    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) {
        std::cerr << "socket() failed\n";
        return -1;
    }

    struct sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(port);
    addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);

    ssize_t n = sendto(sock, message, strlen(message), 0,
                       reinterpret_cast<struct sockaddr *>(&addr), sizeof(addr));
    close(sock);
    return n > 0 ? 0 : -1;
}

int main(int argc, char *argv[])
{
    std::cout << "Hello!\n";

    /* --- Optional UDP send ------------------------------------------------- */
    int udp_port = 0;
    const char *payload = "Hello UDP from example-app!";
    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], "--udp-port") == 0 && i + 1 < argc) {
            udp_port = std::atoi(argv[++i]);
        } else if (std::strcmp(argv[i], "--payload") == 0 && i + 1 < argc) {
            payload = argv[++i];
        }
    }

    if (udp_port > 0) {
        if (send_udp_message(udp_port, payload) == 0) {
            std::cout << "UDP message sent to port " << udp_port << "\n";
        } else {
            std::cerr << "Failed to send UDP message to port " << udp_port << "\n";
        }
    }

    return 0;
}
