CREATE TABLE IF NOT EXISTS `camellia_resource_info` (
  `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
  `url` VARCHAR(1024) NOT NULL,
  `info` VARCHAR(1024) NOT NULL,
  `tids` VARCHAR(1024) DEFAULT NULL,
  `create_time` BIGINT DEFAULT NULL,
  `update_time` BIGINT DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `camellia_table` (
  `tid` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
  `detail` VARCHAR(4096) NOT NULL,
  `info` VARCHAR(1024) NOT NULL,
  `valid_flag` TINYINT DEFAULT NULL,
  `create_time` BIGINT DEFAULT NULL,
  `update_time` BIGINT DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `camellia_table_ref` (
  `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
  `bid` BIGINT NOT NULL,
  `bgroup` VARCHAR(64) NOT NULL,
  `tid` BIGINT NOT NULL,
  `info` VARCHAR(1024) NOT NULL,
  `valid_flag` TINYINT DEFAULT NULL,
  `create_time` BIGINT DEFAULT NULL,
  `update_time` BIGINT DEFAULT NULL,
  UNIQUE KEY `bid_bgroup_unique` (`bid`, `bgroup`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `camellia_ip_checker` (
  `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
  `bid` BIGINT NOT NULL,
  `bgroup` VARCHAR(64) NOT NULL,
  `ipCheckMode` TINYINT NOT NULL,
  `ip_list` VARCHAR(1024) NOT NULL,
  `create_time` BIGINT NOT NULL,
  `update_time` BIGINT NOT NULL,
  UNIQUE KEY `bid_bgroup_unique` (`bid`, `bgroup`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `camellia_rate_limit` (
  `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
  `bid` BIGINT DEFAULT NULL,
  `bgroup` VARCHAR(64) DEFAULT NULL,
  `check_millis` INT NOT NULL DEFAULT 1000,
  `max_count` INT NOT NULL DEFAULT -1,
  `create_time` BIGINT DEFAULT NULL,
  `update_time` BIGINT DEFAULT NULL,
  UNIQUE KEY `bid_bgroup_unique` (`bid`, `bgroup`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
