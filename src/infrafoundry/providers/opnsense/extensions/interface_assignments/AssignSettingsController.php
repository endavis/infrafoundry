<?php

/**
 * @filename    AssignSettingsController.php
 * @package     OPNsense\Interfaces\Api
 * @author      Maciej Szymczak <maciej@szymczak.at> (original)
 * @author      InfraFoundry contributors (fork: IPv6, setItem, getItem,
 *              searchItem, explicit-name-on-add, sessionClose patch)
 * @copyright   (c) 2025 Maciej Szymczak (BSD-2-Clause original)
 * @copyright   (c) 2026 InfraFoundry (fork)
 * @license     BSD-2-Clause
 *
 * Description: OPNsense API endpoint for assigning, configuring, and deleting
 *              logical interfaces (OPTx). Handles creation with static/DHCP/none
 *              IPv4 and static/dhcp/track-interface/none IPv6 configuration,
 *              MAC spoofing, deletion, and in-place update via setItem.
 *
 * Required Path:
 *   /usr/local/opnsense/mvc/app/controllers/OPNsense/Interfaces/Api/AssignSettingsController.php
 *
 * Source / fork rationale:
 *   Forked from https://gist.github.com/szymczag/df152a82e86aff67b984ed3786b027ba
 *   for InfraFoundry issue #715. The base gist provides addItem (auto-numbered)
 *   and delItem only; this fork adds setItem (in-place update), getItem,
 *   searchItem, IPv6 support across add/set, and explicit-name on addItem
 *   (required for cutover continuity). The two community-reported
 *   `$this->sessionClose();` calls have been removed (modern OPNsense versions
 *   reject the call; see Paradoxis comment 2026-02-25 on the gist).
 *
 * Maintenance ownership:
 *   InfraFoundry now owns this code. Upstream gist updates are not auto-
 *   merged. PR-back of the IPv6/setItem extensions to the original gist is
 *   tracked as a follow-up after #715 lands.
 */

namespace OPNsense\Interfaces\Api;

use OPNsense\Base\ApiControllerBase;
use OPNsense\Base\UserException;
use OPNsense\Core\Backend;
use OPNsense\Core\Config;

class AssignSettingsController extends ApiControllerBase
{
    // --- Constants for Configuration Keys and Values ---
    private const CONFIG_KEY_INTERFACES = 'interfaces';
    private const CONFIG_KEY_IF = 'if';
    private const CONFIG_KEY_DESCR = 'descr';
    private const CONFIG_KEY_ENABLE = 'enable';
    private const CONFIG_KEY_SPOOFMAC = 'spoofmac';
    private const CONFIG_KEY_IPADDR = 'ipaddr';
    private const CONFIG_KEY_SUBNET = 'subnet';
    private const CONFIG_KEY_DHCP = 'dhcp';

    // IPv6-specific config keys
    private const CONFIG_KEY_IPADDRV6 = 'ipaddrv6';
    private const CONFIG_KEY_SUBNETV6 = 'subnetv6';
    private const CONFIG_KEY_DHCP6 = 'dhcp6';
    private const CONFIG_KEY_TRACK6_INTERFACE = 'track6-interface';
    private const CONFIG_KEY_TRACK6_PREFIX_ID = 'track6-prefix-id';

    private const IPV4_TYPE_STATIC = 'static';
    private const IPV4_TYPE_DHCP = 'dhcp';
    private const IPV4_TYPE_NONE = 'none';

    private const IPV6_TYPE_STATIC = 'static';
    private const IPV6_TYPE_DHCP = 'dhcp';
    private const IPV6_TYPE_TRACK = 'track-interface';
    private const IPV6_TYPE_NONE = 'none';

    private const BACKEND_INTERFACE_RECONFIGURE = 'interface reconfigure all';

    /**
     * Add and configure a new OPT interface.
     *
     * Creates a new OPT interface (optX), assigns the specified kernel device,
     * description, and optionally configures enable status, MAC spoofing, and
     * IPv4/IPv6 settings.
     *
     * **Validation:** Checks if the specified 'device' is already assigned to
     * another interface before proceeding. If 'name' is supplied (extension),
     * also validates the explicit name is well-formed and unused.
     *
     * Expected JSON payload structure within 'assign' object:
     * {
     *   "assign": {
     *     "device": "vlan0.XXX",         // Required: Kernel device name
     *     "description": "My Interface", // Required: Interface description
     *     "name": "opt5",                // Optional (extension): explicit logical name (^opt\d+$)
     *     "enable": true,                // Optional: defaults to false (disabled)
     *     "spoofMac": "00:11:...",       // Optional
     *     "ipv4Type": "static",          // Optional: "static"|"dhcp"|"none"; defaults "none"
     *     "ipv4Address": "10.1.2.3",     // Required if ipv4Type is "static"
     *     "ipv4Subnet": 24,              // Required if ipv4Type is "static"
     *     "ipv6Type": "track-interface", // Optional: "static"|"dhcp"|"track-interface"|"none"
     *     "ipv6Address": "fd00:...",     // Required if ipv6Type is "static"
     *     "ipv6Subnet": 64,              // Required if ipv6Type is "static"
     *     "ipv6Track": "wan"             // Required if ipv6Type is "track-interface"
     *   }
     * }
     *
     * NOTE: Triggers an 'interface reconfigure all' command upon successful save.
     *
     * @return array Status result including the assigned interface name ('ifname').
     * @throws UserException on invalid input, device already assigned, or configuration errors.
     */
    public function addItemAction()
    {
        $result = ["result" => "failed"];
        $ifname = null;
        $log_prefix = "[AssignSettingsController::addItemAction]";
        error_log("{$log_prefix} --- Request Received ---");

        try {
            error_log("{$log_prefix} Getting JSON payload...");
            $request_body = $this->request->getJsonRawBody(true);
            $data = $request_body['assign'] ?? null;
            error_log("{$log_prefix} Payload data: " . print_r($data, true));

            // --- Basic Payload Validation ---
            if (empty($data) || !is_array($data)) {
                throw new UserException("Invalid payload structure. Expected 'assign' object.");
            }
            $kernel_device = $this->validateDevice($data);
            $description = $this->validateDescription($data);

            // Optional fields parsing and validation
            $enable = filter_var($data['enable'] ?? false, FILTER_VALIDATE_BOOLEAN);
            $spoofMac = $this->validateSpoofMac($data);

            $ipv4 = $this->validateIpv4($data);
            $ipv6 = $this->validateIpv6($data);

            // Optional explicit name (extension; required for cutover continuity).
            $explicit_name = $this->validateExplicitName($data);

            error_log("{$log_prefix} Payload validation complete.");

            // --- Load Config and Check for Existing Device Assignment ---
            $config = Config::getInstance();
            $configHandle = $config->object();

            $this->ensureDeviceUnassigned($configHandle, $kernel_device, $log_prefix);

            // --- Determine Interface Name (explicit if provided, else auto-numbered) ---
            if ($explicit_name !== null) {
                if (isset($configHandle->{self::CONFIG_KEY_INTERFACES}->{$explicit_name})) {
                    throw new UserException("Interface name '{$explicit_name}' already exists.");
                }
                $ifname = $explicit_name;
                error_log("{$log_prefix} Using explicit interface name: {$ifname}");
            } else {
                $ifname = $this->nextOptName($configHandle);
                error_log("{$log_prefix} Determined next available interface name: {$ifname}");
                if (isset($configHandle->{self::CONFIG_KEY_INTERFACES}->{$ifname})) {
                    throw new \Exception("Calculated interface name '{$ifname}' already exists.");
                }
            }

            // --- Apply Configuration ---
            error_log("{$log_prefix} Applying configuration to node '{$ifname}'...");
            $newNode = $configHandle->{self::CONFIG_KEY_INTERFACES}->addChild($ifname);
            $this->applyAssignmentToNode($newNode, $kernel_device, $description, $enable, $spoofMac, $ipv4, $ipv6, $log_prefix, $ifname);

            // --- Save and Apply ---
            error_log("{$log_prefix} Saving configuration changes for '{$ifname}'...");
            $config->save();
            error_log("{$log_prefix} Configuration saved for '{$ifname}'.");

            // Trigger backend reconfigure
            $backend = new Backend();
            $backend_result = $backend->configdRun(self::BACKEND_INTERFACE_RECONFIGURE);
            error_log("{$log_prefix} Backend reconfigure finished. Result: " . trim($backend_result));

            $result['result'] = 'saved';
            $result['ifname'] = $ifname;
            error_log("{$log_prefix} Interface '{$ifname}' created successfully. Returning: " . json_encode($result));
        } catch (UserException $e) {
            error_log("{$log_prefix} UserException: " . $e->getMessage());
            $this->response->setStatusCode(400, "Bad Request");
            $result = ["result" => "failed", "errorMessage" => $e->getMessage()];
        } catch (\Exception $e) {
            $error_details = $e->getMessage() . " (File: " . $e->getFile() . ", Line: " . $e->getLine() . ")";
            error_log("{$log_prefix} CRITICAL EXCEPTION during addItemAction: " . $error_details);
            error_log("{$log_prefix} Trace: " . $e->getTraceAsString());
            $this->response->setStatusCode(500, "Internal Server Error");
            $result = ["result" => "failed", "errorMessage" => "An unexpected server error occurred. Please check logs."];
        }

        error_log("{$log_prefix} --- Request Finished ---");
        return $result;
    }

    /**
     * Update an existing OPT interface in place.
     *
     * Same payload shape as addItem (under 'assign' key). Used for cutover
     * scenarios where a logical interface name (e.g. opt3) needs to be
     * re-bound to a different kernel device without losing its identity.
     *
     * Validation:
     *  - The supplied uuid must exist in <interfaces>.
     *  - Refuses if uuid is 'lan' or 'wan' (mirror delItem safety).
     *  - Per-field validation identical to addItem.
     *  - If 'device' is specified and differs from the current binding,
     *    refuses if the new device is already bound to another interface.
     *
     * @param string $uuid The logical interface name (e.g., 'opt1') to update.
     * @return array ['result' => 'saved', 'ifname' => $uuid] on success.
     * @throws UserException on invalid input, device collision, or unknown uuid.
     */
    public function setItemAction($uuid)
    {
        $result = ["result" => "failed"];
        $log_prefix = "[AssignSettingsController::setItemAction]";
        error_log("{$log_prefix} --- Request Received to UPDATE interface '{$uuid}' ---");

        try {
            // --- Validate uuid ---
            if (empty($uuid)) {
                throw new UserException("Required parameter 'uuid' (logical interface name) is missing.");
            }
            if (!preg_match('/^[a-zA-Z0-9_]+$/', $uuid)) {
                throw new UserException("Invalid format for parameter 'uuid'.");
            }
            if (in_array(strtolower($uuid), ['lan', 'wan'])) {
                throw new UserException("Modification of core interfaces 'lan'/'wan' is not permitted via this action.");
            }

            // --- Get and validate payload ---
            $request_body = $this->request->getJsonRawBody(true);
            $data = $request_body['assign'] ?? null;
            error_log("{$log_prefix} Payload data: " . print_r($data, true));
            if (empty($data) || !is_array($data)) {
                throw new UserException("Invalid payload structure. Expected 'assign' object.");
            }

            $kernel_device = $this->validateDevice($data);
            $description = $this->validateDescription($data);
            $enable = filter_var($data['enable'] ?? false, FILTER_VALIDATE_BOOLEAN);
            $spoofMac = $this->validateSpoofMac($data);
            $ipv4 = $this->validateIpv4($data);
            $ipv6 = $this->validateIpv6($data);
            error_log("{$log_prefix} Payload validation complete.");

            // --- Load config and validate uuid exists ---
            $config = Config::getInstance();
            $configHandle = $config->object();

            if (!isset($configHandle->{self::CONFIG_KEY_INTERFACES}->{$uuid})) {
                throw new UserException("Interface '{$uuid}' does not exist.");
            }

            $existingNode = $configHandle->{self::CONFIG_KEY_INTERFACES}->{$uuid};
            $current_device = isset($existingNode->{self::CONFIG_KEY_IF}) ? (string)$existingNode->{self::CONFIG_KEY_IF} : null;

            // If device is changing, verify the new one isn't bound elsewhere.
            if ($current_device !== $kernel_device) {
                error_log("{$log_prefix} Device changing from '{$current_device}' to '{$kernel_device}'. Verifying no collision...");
                if (isset($configHandle->{self::CONFIG_KEY_INTERFACES})) {
                    foreach ($configHandle->{self::CONFIG_KEY_INTERFACES}->children() as $existing_ifname => $node) {
                        if ((string)$existing_ifname === $uuid) {
                            continue;
                        }
                        if (isset($node->{self::CONFIG_KEY_IF}) && (string)$node->{self::CONFIG_KEY_IF} === $kernel_device) {
                            throw new UserException("Device '{$kernel_device}' is already assigned to interface '{$existing_ifname}'.");
                        }
                    }
                }
            }

            // --- Replace the node's children with fresh values. ---
            // SimpleXMLElement doesn't support a clean "replace all children"; the safest
            // way is to remove and re-create the node. This preserves identity (the name
            // stays the same) but rewrites all assignment-scoped fields.
            unset($configHandle->{self::CONFIG_KEY_INTERFACES}->{$uuid});
            $newNode = $configHandle->{self::CONFIG_KEY_INTERFACES}->addChild($uuid);
            $this->applyAssignmentToNode($newNode, $kernel_device, $description, $enable, $spoofMac, $ipv4, $ipv6, $log_prefix, $uuid);

            // --- Save and Apply ---
            error_log("{$log_prefix} Saving configuration changes for '{$uuid}'...");
            $config->save();
            error_log("{$log_prefix} Configuration saved for '{$uuid}'.");

            $backend = new Backend();
            $backend_result = $backend->configdRun(self::BACKEND_INTERFACE_RECONFIGURE);
            error_log("{$log_prefix} Backend reconfigure finished. Result: " . trim($backend_result));

            $result['result'] = 'saved';
            $result['ifname'] = $uuid;
            error_log("{$log_prefix} Interface '{$uuid}' updated successfully. Returning: " . json_encode($result));
        } catch (UserException $e) {
            error_log("{$log_prefix} UserException: " . $e->getMessage());
            $this->response->setStatusCode(400, "Bad Request");
            $result = ["result" => "failed", "errorMessage" => $e->getMessage()];
        } catch (\Exception $e) {
            $error_details = $e->getMessage() . " (File: " . $e->getFile() . ", Line: " . $e->getLine() . ")";
            error_log("{$log_prefix} CRITICAL EXCEPTION during setItemAction: " . $error_details);
            error_log("{$log_prefix} Trace: " . $e->getTraceAsString());
            $this->response->setStatusCode(500, "Internal Server Error");
            $result = ["result" => "failed", "errorMessage" => "An unexpected server error occurred. Please check logs."];
        }

        error_log("{$log_prefix} --- Request Finished for '{$uuid}' ---");
        return $result;
    }

    /**
     * Fetch a single interface assignment by logical name.
     *
     * @param string $uuid The logical interface name (e.g., 'opt1').
     * @return array {result: 'ok', assign: {...}} on success, or 404 with errorMessage.
     */
    public function getItemAction($uuid)
    {
        $log_prefix = "[AssignSettingsController::getItemAction]";
        error_log("{$log_prefix} --- Request Received for '{$uuid}' ---");

        try {
            if (empty($uuid)) {
                throw new UserException("Required parameter 'uuid' is missing.");
            }
            if (!preg_match('/^[a-zA-Z0-9_]+$/', $uuid)) {
                throw new UserException("Invalid format for parameter 'uuid'.");
            }

            $config = Config::getInstance();
            $configHandle = $config->object();

            if (!isset($configHandle->{self::CONFIG_KEY_INTERFACES}->{$uuid})) {
                $this->response->setStatusCode(404, "Not Found");
                return ["result" => "failed", "errorMessage" => "Interface '{$uuid}' not found."];
            }

            $node = $configHandle->{self::CONFIG_KEY_INTERFACES}->{$uuid};
            $assign = $this->nodeToAssignArray($node);
            return ["result" => "ok", "assign" => $assign];
        } catch (UserException $e) {
            error_log("{$log_prefix} UserException: " . $e->getMessage());
            $this->response->setStatusCode(400, "Bad Request");
            return ["result" => "failed", "errorMessage" => $e->getMessage()];
        } catch (\Exception $e) {
            error_log("{$log_prefix} CRITICAL EXCEPTION: " . $e->getMessage());
            $this->response->setStatusCode(500, "Internal Server Error");
            return ["result" => "failed", "errorMessage" => "An unexpected server error occurred."];
        }
    }

    /**
     * List all interface assignments.
     *
     * Returns rows in OPNsense's standard search response shape so the
     * spike's Python client can consume them with the same parsing code as
     * other 'searchItem' endpoints.
     *
     * @return array {result: 'ok', rows: [...], rowCount: N, total: N, current: 1}
     */
    public function searchItemAction()
    {
        $log_prefix = "[AssignSettingsController::searchItemAction]";
        error_log("{$log_prefix} --- Request Received ---");

        try {
            $config = Config::getInstance();
            $configHandle = $config->object();

            $rows = [];
            if (isset($configHandle->{self::CONFIG_KEY_INTERFACES})) {
                foreach ($configHandle->{self::CONFIG_KEY_INTERFACES}->children() as $ifname => $node) {
                    $row = $this->nodeToAssignArray($node);
                    $row['uuid'] = (string)$ifname;
                    $row['name'] = (string)$ifname;
                    $rows[] = $row;
                }
            }

            $count = count($rows);
            return [
                "result" => "ok",
                "rows" => $rows,
                "rowCount" => $count,
                "total" => $count,
                "current" => 1,
            ];
        } catch (\Exception $e) {
            error_log("{$log_prefix} CRITICAL EXCEPTION: " . $e->getMessage());
            $this->response->setStatusCode(500, "Internal Server Error");
            return ["result" => "failed", "errorMessage" => "An unexpected server error occurred."];
        }
    }

    /**
     * Deletes the configuration node for a specified logical interface.
     * Triggers an interface reconfigure command after saving.
     *
     * @param string $uuid The logical interface name (e.g., 'opt1') to delete.
     * @return array ['result' => 'deleted'] on success or error details.
     * @throws UserException on missing/invalid uuid or attempt to delete core interface.
     */
    public function delItemAction($uuid)
    {
        $result = ["result" => "failed"];
        $log_prefix = "[AssignSettingsController::delItemAction]";
        error_log("{$log_prefix} --- Request Received to DELETE interface '{$uuid}' ---");

        try {
            if (empty($uuid)) {
                throw new UserException(gettext("Required parameter 'uuid' (logical interface name) is missing."));
            }
            if (!preg_match('/^[a-zA-Z0-9_]+$/', $uuid)) {
                throw new UserException(gettext("Invalid format for parameter 'uuid'."));
            }
            if (in_array(strtolower($uuid), ['lan', 'wan'])) {
                throw new UserException(gettext("Deletion of core interfaces like 'lan' or 'wan' is not permitted via this action."));
            }

            error_log("{$log_prefix} Loading configuration to delete '{$uuid}'...");
            $config = Config::getInstance();
            $configHandle = $config->object();

            if (!isset($configHandle->{self::CONFIG_KEY_INTERFACES}->{$uuid})) {
                error_log("{$log_prefix} Interface '{$uuid}' not found. Idempotent success.");
                return ["result" => "deleted", "message" => "Interface '{$uuid}' not found, assumed already deleted."];
            }

            unset($configHandle->{self::CONFIG_KEY_INTERFACES}->{$uuid});
            error_log("{$log_prefix} Removed interface node '{$uuid}'.");

            $config->save();
            error_log("{$log_prefix} Configuration saved.");

            $backend = new Backend();
            $backend_result = $backend->configdRun(self::BACKEND_INTERFACE_RECONFIGURE);
            error_log("{$log_prefix} Backend reconfigure finished. Result: " . trim($backend_result));

            $result = ["result" => "deleted"];
            error_log("{$log_prefix} Successfully deleted '{$uuid}'.");
        } catch (UserException $e) {
            error_log("{$log_prefix} UserException: " . $e->getMessage());
            $this->response->setStatusCode(400, "Bad Request");
            $result = ["result" => "failed", "errorMessage" => $e->getMessage()];
        } catch (\Exception $e) {
            $error_details = $e->getMessage() . " (File: " . $e->getFile() . ", Line: " . $e->getLine() . ")";
            error_log("{$log_prefix} CRITICAL EXCEPTION during deletion of '{$uuid}': " . $error_details);
            error_log("{$log_prefix} Trace: " . $e->getTraceAsString());
            $this->response->setStatusCode(500, "Internal Server Error");
            $result = ["result" => "failed", "errorMessage" => "An unexpected server error occurred during deletion. Please check logs."];
        }

        error_log("{$log_prefix} --- Request Finished for '{$uuid}' ---");
        return $result;
    }

    // ------------------------------------------------------------------
    // Validation helpers (extracted from addItem for reuse in setItem)
    // ------------------------------------------------------------------

    private function validateDevice(array $data): string
    {
        if (empty($data['device']) || !is_string($data['device'])) {
            throw new UserException("Payload missing required 'device' field (string).");
        }
        $kernel_device = trim($data['device']);
        if (!preg_match('/^[a-zA-Z0-9_.\-]+$/', $kernel_device)) {
            throw new UserException("Invalid format for 'device' field '{$kernel_device}'.");
        }
        return $kernel_device;
    }

    private function validateDescription(array $data): string
    {
        if (empty($data['description']) || !is_string($data['description'])) {
            throw new UserException("Payload missing required 'description' field (string).");
        }
        return trim($data['description']);
    }

    private function validateSpoofMac(array $data): ?string
    {
        if (!isset($data['spoofMac'])) {
            return null;
        }
        $spoofMac = trim($data['spoofMac']);
        if ($spoofMac === '') {
            return null;
        }
        if (!filter_var($spoofMac, FILTER_VALIDATE_MAC)) {
            throw new UserException("Invalid format for 'spoofMac' field. Expected standard MAC address format.");
        }
        return $spoofMac;
    }

    /**
     * @return array{type: string, address: ?string, subnet: ?int}
     */
    private function validateIpv4(array $data): array
    {
        $type = isset($data['ipv4Type']) ? trim(strtolower($data['ipv4Type'])) : self::IPV4_TYPE_NONE;
        $allowed = [self::IPV4_TYPE_STATIC, self::IPV4_TYPE_DHCP, self::IPV4_TYPE_NONE];
        if (!in_array($type, $allowed, true)) {
            throw new UserException("Invalid 'ipv4Type'. Allowed: " . implode(', ', $allowed));
        }
        $address = isset($data['ipv4Address']) ? trim($data['ipv4Address']) : null;
        $subnet = $data['ipv4Subnet'] ?? null;

        if ($type === self::IPV4_TYPE_STATIC) {
            if (empty($address) || filter_var($address, FILTER_VALIDATE_IP, FILTER_FLAG_IPV4) === false) {
                throw new UserException("Invalid or missing 'ipv4Address' for ipv4Type 'static'.");
            }
            if ($subnet === null || !filter_var($subnet, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1, 'max_range' => 32]])) {
                throw new UserException("Invalid or missing 'ipv4Subnet' for ipv4Type 'static'. Expected integer 1-32.");
            }
            return ['type' => $type, 'address' => $address, 'subnet' => intval($subnet)];
        }

        if (!empty($address) || $subnet !== null) {
            throw new UserException("'ipv4Address'/'ipv4Subnet' should only be provided when ipv4Type is 'static'.");
        }
        return ['type' => $type, 'address' => null, 'subnet' => null];
    }

    /**
     * @return array{type: string, address: ?string, subnet: ?int, track: ?string}
     */
    private function validateIpv6(array $data): array
    {
        $type = isset($data['ipv6Type']) ? trim(strtolower($data['ipv6Type'])) : self::IPV6_TYPE_NONE;
        $allowed = [self::IPV6_TYPE_STATIC, self::IPV6_TYPE_DHCP, self::IPV6_TYPE_TRACK, self::IPV6_TYPE_NONE];
        if (!in_array($type, $allowed, true)) {
            throw new UserException("Invalid 'ipv6Type'. Allowed: " . implode(', ', $allowed));
        }
        $address = isset($data['ipv6Address']) ? trim($data['ipv6Address']) : null;
        $subnet = $data['ipv6Subnet'] ?? null;
        $track = isset($data['ipv6Track']) ? trim($data['ipv6Track']) : null;

        if ($type === self::IPV6_TYPE_STATIC) {
            if (empty($address) || filter_var($address, FILTER_VALIDATE_IP, FILTER_FLAG_IPV6) === false) {
                throw new UserException("Invalid or missing 'ipv6Address' for ipv6Type 'static'.");
            }
            if ($subnet === null || !filter_var($subnet, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1, 'max_range' => 128]])) {
                throw new UserException("Invalid or missing 'ipv6Subnet' for ipv6Type 'static'. Expected integer 1-128.");
            }
            if ($track !== null && $track !== '') {
                throw new UserException("'ipv6Track' should not be provided when ipv6Type is 'static'.");
            }
            return ['type' => $type, 'address' => $address, 'subnet' => intval($subnet), 'track' => null];
        }

        if ($type === self::IPV6_TYPE_TRACK) {
            if (empty($track) || !preg_match('/^[a-zA-Z0-9_]+$/', $track)) {
                throw new UserException("Invalid or missing 'ipv6Track' for ipv6Type 'track-interface'. Expected logical interface identifier (e.g., 'wan').");
            }
            if (!empty($address) || $subnet !== null) {
                throw new UserException("'ipv6Address'/'ipv6Subnet' should not be provided when ipv6Type is 'track-interface'.");
            }
            return ['type' => $type, 'address' => null, 'subnet' => null, 'track' => $track];
        }

        // dhcp / none — no extra fields permitted.
        if (!empty($address) || $subnet !== null || ($track !== null && $track !== '')) {
            throw new UserException("'ipv6Address'/'ipv6Subnet'/'ipv6Track' only valid for ipv6Type 'static' or 'track-interface'.");
        }
        return ['type' => $type, 'address' => null, 'subnet' => null, 'track' => null];
    }

    private function validateExplicitName(array $data): ?string
    {
        if (!isset($data['name'])) {
            return null;
        }
        $name = is_string($data['name']) ? trim($data['name']) : '';
        if ($name === '') {
            return null;
        }
        if (!preg_match('/^opt\d+$/', $name)) {
            throw new UserException("Invalid 'name' field '{$name}'. Expected pattern: ^opt\\d+$ (e.g., 'opt5'). 'lan'/'wan' not permitted.");
        }
        return $name;
    }

    /**
     * Refuse if the kernel device is already bound to another logical interface.
     */
    private function ensureDeviceUnassigned(\SimpleXMLElement $configHandle, string $kernel_device, string $log_prefix): void
    {
        if (!isset($configHandle->{self::CONFIG_KEY_INTERFACES})) {
            return;
        }
        foreach ($configHandle->{self::CONFIG_KEY_INTERFACES}->children() as $existing_ifname => $node) {
            if (isset($node->{self::CONFIG_KEY_IF}) && (string)$node->{self::CONFIG_KEY_IF} === $kernel_device) {
                $msg = "Device '{$kernel_device}' is already assigned to interface '{$existing_ifname}'.";
                error_log("{$log_prefix} {$msg}");
                throw new UserException($msg);
            }
        }
    }

    private function nextOptName(\SimpleXMLElement $configHandle): string
    {
        $max_opt_num = 0;
        if (isset($configHandle->{self::CONFIG_KEY_INTERFACES})) {
            foreach ($configHandle->{self::CONFIG_KEY_INTERFACES}->children() as $current_ifname => $node) {
                if (preg_match('/^opt(\d+)$/', (string)$current_ifname, $matches)) {
                    $num = intval($matches[1]);
                    if ($num > $max_opt_num) {
                        $max_opt_num = $num;
                    }
                }
            }
        }
        return "opt" . ($max_opt_num + 1);
    }

    /**
     * Apply the validated assignment payload onto a SimpleXMLElement node.
     *
     * @param array{type: string, address: ?string, subnet: ?int} $ipv4
     * @param array{type: string, address: ?string, subnet: ?int, track: ?string} $ipv6
     */
    private function applyAssignmentToNode(\SimpleXMLElement $node, string $kernel_device, string $description, bool $enable, ?string $spoofMac, array $ipv4, array $ipv6, string $log_prefix, string $ifname): void
    {
        $node->{self::CONFIG_KEY_IF} = $kernel_device;
        $node->{self::CONFIG_KEY_DESCR} = $description;

        if ($enable) {
            $node->addChild(self::CONFIG_KEY_ENABLE, '1');
        }
        if ($spoofMac !== null) {
            $node->{self::CONFIG_KEY_SPOOFMAC} = $spoofMac;
        }

        // --- IPv4 ---
        switch ($ipv4['type']) {
            case self::IPV4_TYPE_STATIC:
                $node->{self::CONFIG_KEY_IPADDR} = $ipv4['address'];
                $node->{self::CONFIG_KEY_SUBNET} = $ipv4['subnet'];
                if (isset($node->{self::CONFIG_KEY_DHCP})) {
                    unset($node->{self::CONFIG_KEY_DHCP});
                }
                break;
            case self::IPV4_TYPE_DHCP:
                $node->{self::CONFIG_KEY_IPADDR} = self::IPV4_TYPE_DHCP;
                if (isset($node->{self::CONFIG_KEY_SUBNET})) {
                    unset($node->{self::CONFIG_KEY_SUBNET});
                }
                $node->addChild(self::CONFIG_KEY_DHCP, '');
                break;
            case self::IPV4_TYPE_NONE:
            default:
                if (isset($node->{self::CONFIG_KEY_IPADDR})) {
                    unset($node->{self::CONFIG_KEY_IPADDR});
                }
                if (isset($node->{self::CONFIG_KEY_SUBNET})) {
                    unset($node->{self::CONFIG_KEY_SUBNET});
                }
                if (isset($node->{self::CONFIG_KEY_DHCP})) {
                    unset($node->{self::CONFIG_KEY_DHCP});
                }
                break;
        }

        // --- IPv6 ---
        switch ($ipv6['type']) {
            case self::IPV6_TYPE_STATIC:
                $node->{self::CONFIG_KEY_IPADDRV6} = $ipv6['address'];
                $node->{self::CONFIG_KEY_SUBNETV6} = $ipv6['subnet'];
                if (isset($node->{self::CONFIG_KEY_DHCP6})) {
                    unset($node->{self::CONFIG_KEY_DHCP6});
                }
                if (isset($node->{self::CONFIG_KEY_TRACK6_INTERFACE})) {
                    unset($node->{self::CONFIG_KEY_TRACK6_INTERFACE});
                }
                if (isset($node->{self::CONFIG_KEY_TRACK6_PREFIX_ID})) {
                    unset($node->{self::CONFIG_KEY_TRACK6_PREFIX_ID});
                }
                break;
            case self::IPV6_TYPE_DHCP:
                $node->{self::CONFIG_KEY_IPADDRV6} = self::IPV6_TYPE_DHCP;
                if (isset($node->{self::CONFIG_KEY_SUBNETV6})) {
                    unset($node->{self::CONFIG_KEY_SUBNETV6});
                }
                $node->addChild(self::CONFIG_KEY_DHCP6, '');
                if (isset($node->{self::CONFIG_KEY_TRACK6_INTERFACE})) {
                    unset($node->{self::CONFIG_KEY_TRACK6_INTERFACE});
                }
                if (isset($node->{self::CONFIG_KEY_TRACK6_PREFIX_ID})) {
                    unset($node->{self::CONFIG_KEY_TRACK6_PREFIX_ID});
                }
                break;
            case self::IPV6_TYPE_TRACK:
                $node->{self::CONFIG_KEY_IPADDRV6} = 'track6';
                $node->{self::CONFIG_KEY_TRACK6_INTERFACE} = $ipv6['track'];
                $node->addChild(self::CONFIG_KEY_TRACK6_PREFIX_ID, '0');
                if (isset($node->{self::CONFIG_KEY_SUBNETV6})) {
                    unset($node->{self::CONFIG_KEY_SUBNETV6});
                }
                if (isset($node->{self::CONFIG_KEY_DHCP6})) {
                    unset($node->{self::CONFIG_KEY_DHCP6});
                }
                break;
            case self::IPV6_TYPE_NONE:
            default:
                if (isset($node->{self::CONFIG_KEY_IPADDRV6})) {
                    unset($node->{self::CONFIG_KEY_IPADDRV6});
                }
                if (isset($node->{self::CONFIG_KEY_SUBNETV6})) {
                    unset($node->{self::CONFIG_KEY_SUBNETV6});
                }
                if (isset($node->{self::CONFIG_KEY_DHCP6})) {
                    unset($node->{self::CONFIG_KEY_DHCP6});
                }
                if (isset($node->{self::CONFIG_KEY_TRACK6_INTERFACE})) {
                    unset($node->{self::CONFIG_KEY_TRACK6_INTERFACE});
                }
                if (isset($node->{self::CONFIG_KEY_TRACK6_PREFIX_ID})) {
                    unset($node->{self::CONFIG_KEY_TRACK6_PREFIX_ID});
                }
                break;
        }
        error_log("{$log_prefix} Applied assignment to '{$ifname}': device={$kernel_device}, ipv4={$ipv4['type']}, ipv6={$ipv6['type']}");
    }

    /**
     * Convert a config <opt1>...</opt1> node back to a flat assoc array
     * suitable for getItem/searchItem JSON responses.
     */
    private function nodeToAssignArray(\SimpleXMLElement $node): array
    {
        $out = [
            'device' => isset($node->{self::CONFIG_KEY_IF}) ? (string)$node->{self::CONFIG_KEY_IF} : '',
            'description' => isset($node->{self::CONFIG_KEY_DESCR}) ? (string)$node->{self::CONFIG_KEY_DESCR} : '',
            'enable' => isset($node->{self::CONFIG_KEY_ENABLE}) ? ((string)$node->{self::CONFIG_KEY_ENABLE} === '1') : false,
            'spoofMac' => isset($node->{self::CONFIG_KEY_SPOOFMAC}) ? (string)$node->{self::CONFIG_KEY_SPOOFMAC} : null,
        ];

        // Reverse-map IPv4
        $ipaddr = isset($node->{self::CONFIG_KEY_IPADDR}) ? (string)$node->{self::CONFIG_KEY_IPADDR} : '';
        if ($ipaddr === self::IPV4_TYPE_DHCP) {
            $out['ipv4Type'] = self::IPV4_TYPE_DHCP;
            $out['ipv4Address'] = null;
            $out['ipv4Subnet'] = null;
        } elseif ($ipaddr !== '') {
            $out['ipv4Type'] = self::IPV4_TYPE_STATIC;
            $out['ipv4Address'] = $ipaddr;
            $out['ipv4Subnet'] = isset($node->{self::CONFIG_KEY_SUBNET}) ? intval((string)$node->{self::CONFIG_KEY_SUBNET}) : null;
        } else {
            $out['ipv4Type'] = self::IPV4_TYPE_NONE;
            $out['ipv4Address'] = null;
            $out['ipv4Subnet'] = null;
        }

        // Reverse-map IPv6
        $ipaddrv6 = isset($node->{self::CONFIG_KEY_IPADDRV6}) ? (string)$node->{self::CONFIG_KEY_IPADDRV6} : '';
        if ($ipaddrv6 === self::IPV6_TYPE_DHCP) {
            $out['ipv6Type'] = self::IPV6_TYPE_DHCP;
            $out['ipv6Address'] = null;
            $out['ipv6Subnet'] = null;
            $out['ipv6Track'] = null;
        } elseif ($ipaddrv6 === 'track6' || isset($node->{self::CONFIG_KEY_TRACK6_INTERFACE})) {
            $out['ipv6Type'] = self::IPV6_TYPE_TRACK;
            $out['ipv6Address'] = null;
            $out['ipv6Subnet'] = null;
            $out['ipv6Track'] = isset($node->{self::CONFIG_KEY_TRACK6_INTERFACE}) ? (string)$node->{self::CONFIG_KEY_TRACK6_INTERFACE} : null;
        } elseif ($ipaddrv6 !== '') {
            $out['ipv6Type'] = self::IPV6_TYPE_STATIC;
            $out['ipv6Address'] = $ipaddrv6;
            $out['ipv6Subnet'] = isset($node->{self::CONFIG_KEY_SUBNETV6}) ? intval((string)$node->{self::CONFIG_KEY_SUBNETV6}) : null;
            $out['ipv6Track'] = null;
        } else {
            $out['ipv6Type'] = self::IPV6_TYPE_NONE;
            $out['ipv6Address'] = null;
            $out['ipv6Subnet'] = null;
            $out['ipv6Track'] = null;
        }

        return $out;
    }
}
