-- MySQL dump 10.13  Distrib 5.7.26, for Win64 (x86_64)
--
-- Host: localhost    Database: xbot
-- ------------------------------------------------------
-- Server version	5.7.26

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `conversation_history`
--

DROP TABLE IF EXISTS `conversation_history`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `conversation_history` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `buyer_name` varchar(255) NOT NULL,
  `role` varchar(50) NOT NULL,
  `content` text NOT NULL,
  `coze_conversation_id` varchar(255) DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=345 DEFAULT CHARSET=utf8mb4;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `conversation_history`
--

LOCK TABLES `conversation_history` WRITE;
/*!40000 ALTER TABLE `conversation_history` DISABLE KEYS */;
INSERT INTO `conversation_history` VALUES (337,'敌法师爱码','user','在吗','7593074481959125027','2026-01-09 03:28:58'),(338,'敌法师爱码','assistant','抱歉，等待回复超时，请稍后再试。','7593074481959125027','2026-01-09 03:28:58'),(339,'敌法师爱码','user','你好','7593074481959125027','2026-01-09 16:07:48'),(340,'敌法师爱码','assistant','嗯嗯','7593074481959125027','2026-01-09 16:07:48'),(341,'敌法师爱码','user','我喜欢吃苹果','7593074481959125027','2026-01-09 16:08:05'),(342,'敌法师爱码','assistant','您好！请问您是想了解苹果相关的信息，还是需要其他帮助呢？','7593074481959125027','2026-01-09 16:08:05'),(343,'敌法师爱码','user','我刚刚说我喜欢吃什么','7593074481959125027','2026-01-09 16:08:16'),(344,'敌法师爱码','assistant','您刚刚说您喜欢吃苹果，有什么需要我帮忙的吗？','7593074481959125027','2026-01-09 16:08:16');
/*!40000 ALTER TABLE `conversation_history` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `user_sessions`
--

DROP TABLE IF EXISTS `user_sessions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `user_sessions` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` varchar(50) NOT NULL COMMENT '闲鱼用户唯一ID',
  `item_id` varchar(50) NOT NULL COMMENT '商品ID',
  `buyer_name` varchar(255) DEFAULT NULL COMMENT '买家昵称',
  `conversation_id` varchar(255) DEFAULT NULL COMMENT 'Coze会话ID',
  `summary` text COMMENT '会话摘要',
  `inactive_sent` tinyint(1) DEFAULT '0' COMMENT '是否已发送过inactive',
  `customer_type` varchar(20) DEFAULT 'new' COMMENT '客户类型: new/returning',
  `order_status` varchar(50) DEFAULT NULL COMMENT '订单状态',
  `last_message_at` datetime DEFAULT NULL COMMENT '最后消息时间',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_user_item` (`user_id`,`item_id`)
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `user_sessions`
--

LOCK TABLES `user_sessions` WRITE;
/*!40000 ALTER TABLE `user_sessions` DISABLE KEYS */;
INSERT INTO `user_sessions` VALUES (7,'2221014675410','unknown','敌法师爱码','7593074481959125027',NULL,0,'new','已完成','2026-01-09 16:08:16','2026-01-09 03:28:19','2026-01-09 16:08:16');
/*!40000 ALTER TABLE `user_sessions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `users` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `buyer_name` varchar(255) NOT NULL,
  `coze_conversation_id` varchar(255) DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `is_whitelist` tinyint(1) DEFAULT '0',
  PRIMARY KEY (`id`),
  UNIQUE KEY `buyer_name` (`buyer_name`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `users`
--

LOCK TABLES `users` WRITE;
/*!40000 ALTER TABLE `users` DISABLE KEYS */;
INSERT INTO `users` VALUES (2,'敌法师爱码','7593074481959125027','2026-01-06 19:43:15','2026-01-09 03:28:19',1),(4,'秦朝码代码','7593064846171144232','2026-01-07 17:37:56','2026-01-09 02:50:59',0);
/*!40000 ALTER TABLE `users` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-01-09 16:09:26
