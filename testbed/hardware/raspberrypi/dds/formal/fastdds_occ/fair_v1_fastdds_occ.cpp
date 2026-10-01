#include <atomic>
#include <chrono>
#include <csignal>
#include <cctype>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <mutex>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>

#include <fastdds/dds/domain/DomainParticipant.hpp>
#include <fastdds/dds/domain/DomainParticipantFactory.hpp>
#include <fastdds/dds/publisher/DataWriter.hpp>
#include <fastdds/dds/publisher/Publisher.hpp>
#include <fastdds/dds/subscriber/DataReader.hpp>
#include <fastdds/dds/subscriber/DataReaderListener.hpp>
#include <fastdds/dds/subscriber/Subscriber.hpp>
#include <fastdds/dds/topic/Topic.hpp>
#include <fastdds/dds/topic/TypeSupport.hpp>

#include "fair_v1_dds.h"
#include "fair_v1_ddsPubSubTypes.h"

using namespace eprosima::fastdds::dds;

static constexpr const char* DATASET_SCHEMA_VERSION = "1.0";
static constexpr const char* TELEMETRY_TOPIC = "fair_v1_vm001_telemetry";
static constexpr const char* ECHO_TOPIC = "fair_v1_vm001_echo";

static std::atomic<bool> running{true};

static int64_t now_us()
{
    return std::chrono::duration_cast<std::chrono::microseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
}

static void stop_handler(int)
{
    running = false;
}

static std::string lowercase(std::string s)
{
    for (char& c : s)
    {
        c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    }
    return s;
}

static std::string uppercase(std::string s)
{
    for (char& c : s)
    {
        c = static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
    }
    return s;
}

static std::string json_escape(const std::string& s)
{
    std::ostringstream out;

    for (unsigned char c : s)
    {
        switch (c)
        {
            case '"':  out << "\\\""; break;
            case '\\': out << "\\\\"; break;
            case '\b': out << "\\b";  break;
            case '\f': out << "\\f";  break;
            case '\n': out << "\\n";  break;
            case '\r': out << "\\r";  break;
            case '\t': out << "\\t";  break;

            default:
                if (c < 0x20)
                {
                    out << "\\u"
                        << std::hex
                        << std::setw(4)
                        << std::setfill('0')
                        << static_cast<int>(c)
                        << std::dec;
                }
                else
                {
                    out << static_cast<char>(c);
                }
        }
    }

    return out.str();
}

static std::string uuid_v4()
{
    static thread_local std::mt19937_64 rng(std::random_device{}());

    unsigned char b[16];

    for (auto& v : b)
    {
        v = static_cast<unsigned char>(rng() & 0xff);
    }

    b[6] = static_cast<unsigned char>((b[6] & 0x0f) | 0x40);
    b[8] = static_cast<unsigned char>((b[8] & 0x3f) | 0x80);

    std::ostringstream out;
    out << std::hex << std::setfill('0');

    for (int i = 0; i < 16; ++i)
    {
        out << std::setw(2) << static_cast<int>(b[i]);

        if (i == 3 || i == 5 || i == 7 || i == 9)
        {
            out << '-';
        }
    }

    return out.str();
}

struct Options
{
    int domain = 0;
    std::string profile;
    std::string run_id;
    std::string clock_domain;
    std::string service_id;
    std::string event_log;
};

static void usage(const char* prog)
{
    std::cerr
        << "Usage: " << prog
        << " --profile c0|c1|c2"
        << " [--domain N]"
        << " --run-id ID"
        << " --clock-domain NAME"
        << " --service-id ID"
        << " --event-log PATH"
        << std::endl;
}

static Options parse_args(int argc, char** argv)
{
    Options o;

    for (int i = 1; i < argc; ++i)
    {
        std::string a = argv[i];

        auto value = [&](const char* name) -> std::string
        {
            if (i + 1 >= argc)
            {
                throw std::runtime_error(std::string("missing value for ") + name);
            }

            return argv[++i];
        };

        if (a == "--domain")
        {
            o.domain = std::stoi(value("--domain"));
        }
        else if (a == "--profile")
        {
            o.profile = lowercase(value("--profile"));
        }
        else if (a == "--run-id")
        {
            o.run_id = value("--run-id");
        }
        else if (a == "--clock-domain")
        {
            o.clock_domain = value("--clock-domain");
        }
        else if (a == "--service-id")
        {
            o.service_id = value("--service-id");
        }
        else if (a == "--event-log")
        {
            o.event_log = value("--event-log");
        }
        else if (a == "--help" || a == "-h")
        {
            usage(argv[0]);
            std::exit(0);
        }
        else
        {
            throw std::runtime_error("unknown argument: " + a);
        }
    }

    if (o.profile != "c0" && o.profile != "c1" && o.profile != "c2")
    {
        throw std::runtime_error("--profile must be c0, c1, or c2");
    }

    if (o.run_id.empty() ||
        o.clock_domain.empty() ||
        o.service_id.empty() ||
        o.event_log.empty())
    {
        throw std::runtime_error("required argument missing");
    }

    return o;
}

class EventLogger
{
public:
    EventLogger(
        const std::string& path,
        std::string run_id,
        std::string clock_domain,
        std::string service_id)
        : run_id_(std::move(run_id))
        , clock_domain_(std::move(clock_domain))
        , service_id_(std::move(service_id))
    {
        if (std::filesystem::exists(path))
        {
            throw std::runtime_error(
                "event log already exists; refusing to overwrite/mix evidence: " + path);
        }

        file_.open(path, std::ios::out | std::ios::trunc);

        if (!file_)
        {
            throw std::runtime_error("cannot open event log: " + path);
        }
    }

    void write(
        const FairV1Telemetry& telemetry,
        const char* event_type,
        int64_t event_time_us)
    {
        std::lock_guard<std::mutex> lock(mutex_);

        file_
            << "{\"clock_domain\":\"" << json_escape(clock_domain_)
            << "\",\"dataset_schema_version\":\"" << DATASET_SCHEMA_VERSION
            << "\",\"event_id\":\"" << uuid_v4()
            << "\",\"event_source_layer\":\"fair_echo_application"
            << "\",\"event_time_us\":" << event_time_us
            << ",\"event_type\":\"" << event_type
            << "\",\"protocol\":\"dds"
            << "\",\"protocol_correlation\":{"
            << "\"dds_reliability\":\"RELIABLE\","
            << "\"echo_topic\":\"" << ECHO_TOPIC << "\","
            << "\"telemetry_topic\":\"" << TELEMETRY_TOPIC << "\"}"
            << ",\"run_id\":\"" << json_escape(run_id_)
            << "\",\"seq\":" << telemetry.seq()
            << ",\"serialNumber\":\"" << json_escape(telemetry.serialNumber())
            << "\",\"service_id\":\"" << json_escape(service_id_)
            << "\"}"
            << '\n';

        file_.flush();
    }

private:
    std::ofstream file_;
    std::mutex mutex_;
    std::string run_id_;
    std::string clock_domain_;
    std::string service_id_;
};

class TelemetryListener : public DataReaderListener
{
public:
    TelemetryListener(
        DataWriter* writer,
        EventLogger& logger)
        : writer_(writer)
        , logger_(logger)
    {
    }

    void on_data_available(DataReader* reader) override
    {
        // Frozen FAIR-V1 boundary:
        // timestamp at DataReader callback/handler entry.
        const int64_t t_occ_rx_us = now_us();

        FairV1Telemetry telemetry;
        SampleInfo info;

        while (reader->take_next_sample(&telemetry, &info) ==
                eprosima::fastrtps::types::ReturnCode_t::RETCODE_OK)
        {
            if (!info.valid_data)
            {
                continue;
            }

            logger_.write(
                telemetry,
                "occ_rx",
                t_occ_rx_us);

            FairV1Echo echo;
            echo.serialNumber(telemetry.serialNumber());
            echo.seq(telemetry.seq());

            // Frozen FAIR-V1 boundary:
            // immediately before DataWriter.write().
            const int64_t t_occ_tx_us = now_us();

            const bool write_ok = writer_->write(&echo);

            if (!write_ok)
            {
                std::cerr
                    << "FAIL: echo DataWriter.write seq="
                    << telemetry.seq()
                    << std::endl;
                continue;
            }

            logger_.write(
                telemetry,
                "occ_tx",
                t_occ_tx_us);
        }
    }

private:
    DataWriter* writer_;
    EventLogger& logger_;
};

static void configure_security(
    DomainParticipantQos& pqos,
    const std::string& profile)
{
    if (profile == "c0")
    {
        return;
    }

    auto& props = pqos.properties().properties();

    props.emplace_back(
        "dds.sec.auth.plugin",
        "builtin.PKI-DH");

    props.emplace_back(
        "dds.sec.auth.builtin.PKI-DH.identity_ca",
        "file:///opt/fair-v1/dds/security/identity_ca_cert.pem");

    props.emplace_back(
        "dds.sec.auth.builtin.PKI-DH.identity_certificate",
        "file:///opt/fair-v1/dds/security/occ_cert.pem");

    props.emplace_back(
        "dds.sec.auth.builtin.PKI-DH.private_key",
        "file:///opt/fair-v1/dds/security/private/occ_key.pem");

    props.emplace_back(
        "dds.sec.access.plugin",
        "builtin.Access-Permissions");

    props.emplace_back(
        "dds.sec.access.builtin.Access-Permissions.permissions_ca",
        "file:///opt/fair-v1/dds/security/permissions_ca_cert.pem");

    props.emplace_back(
        "dds.sec.access.builtin.Access-Permissions.governance",
        profile == "c1"
            ? "file:///opt/fair-v1/dds/security/governance_c1.p7s"
            : "file:///opt/fair-v1/dds/security/governance_c2.p7s");

    props.emplace_back(
        "dds.sec.access.builtin.Access-Permissions.permissions",
        "file:///opt/fair-v1/dds/security/permissions_occ.p7s");

    props.emplace_back(
        "dds.sec.crypto.plugin",
        "builtin.AES-GCM-GMAC");
}

int main(int argc, char** argv)
{
    try
    {
        const Options opts = parse_args(argc, argv);

        std::signal(SIGINT, stop_handler);
        std::signal(SIGTERM, stop_handler);

        EventLogger event_logger(
            opts.event_log,
            opts.run_id,
            opts.clock_domain,
            opts.service_id);

        DomainParticipantQos pqos;
        pqos.name(
            ("FAIR_V1_DDS_OCC_" + uppercase(opts.profile)).c_str());

        configure_security(
            pqos,
            opts.profile);

        DomainParticipant* participant =
            DomainParticipantFactory::get_instance()->create_participant(
                opts.domain,
                pqos);

        if (participant == nullptr)
        {
            std::cerr << "FAIL: create_participant" << std::endl;
            return 1;
        }

        TypeSupport telemetry_type(new FairV1TelemetryPubSubType());
        TypeSupport echo_type(new FairV1EchoPubSubType());

        telemetry_type.register_type(participant);
        echo_type.register_type(participant);

        Topic* telemetry_topic =
            participant->create_topic(
                TELEMETRY_TOPIC,
                telemetry_type.get_type_name(),
                TOPIC_QOS_DEFAULT);

        Topic* echo_topic =
            participant->create_topic(
                ECHO_TOPIC,
                echo_type.get_type_name(),
                TOPIC_QOS_DEFAULT);

        if (telemetry_topic == nullptr || echo_topic == nullptr)
        {
            std::cerr << "FAIL: create_topic" << std::endl;
            return 2;
        }

        Publisher* publisher =
            participant->create_publisher(PUBLISHER_QOS_DEFAULT);

        Subscriber* subscriber =
            participant->create_subscriber(SUBSCRIBER_QOS_DEFAULT);

        if (publisher == nullptr || subscriber == nullptr)
        {
            std::cerr << "FAIL: publisher/subscriber" << std::endl;
            return 3;
        }

        DataWriterQos writer_qos = DATAWRITER_QOS_DEFAULT;
        writer_qos.reliability().kind = RELIABLE_RELIABILITY_QOS;
        writer_qos.durability().kind = VOLATILE_DURABILITY_QOS;
        writer_qos.history().kind = KEEP_LAST_HISTORY_QOS;
        writer_qos.history().depth = 32;

        DataReaderQos reader_qos = DATAREADER_QOS_DEFAULT;
        reader_qos.reliability().kind = RELIABLE_RELIABILITY_QOS;
        reader_qos.durability().kind = VOLATILE_DURABILITY_QOS;
        reader_qos.history().kind = KEEP_LAST_HISTORY_QOS;
        reader_qos.history().depth = 32;

        DataWriter* echo_writer =
            publisher->create_datawriter(
                echo_topic,
                writer_qos);

        if (echo_writer == nullptr)
        {
            std::cerr << "FAIL: create echo writer" << std::endl;
            return 4;
        }

        TelemetryListener listener(
            echo_writer,
            event_logger);

        DataReader* telemetry_reader =
            subscriber->create_datareader(
                telemetry_topic,
                reader_qos,
                &listener);

        if (telemetry_reader == nullptr)
        {
            std::cerr << "FAIL: create telemetry reader" << std::endl;
            return 5;
        }

        // Preserve canonical launcher health-check contract.
        std::cout
            << "FAIR-V1 DDS OCC application ready"
            << std::endl;

        while (running)
        {
            std::this_thread::sleep_for(
                std::chrono::milliseconds(200));
        }

        participant->delete_contained_entities();

        DomainParticipantFactory::get_instance()
            ->delete_participant(participant);

        return 0;
    }
    catch (const std::exception& e)
    {
        usage(argv[0]);

        std::cerr
            << "FAIL: "
            << e.what()
            << std::endl;

        return 64;
    }
}
