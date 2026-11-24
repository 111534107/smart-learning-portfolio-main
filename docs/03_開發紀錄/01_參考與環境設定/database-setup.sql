CREATE DATABASE IF NOT EXISTS smart_learning_portfolio
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'smart_learning_app'@'localhost'
  IDENTIFIED BY 'change-this-password';

GRANT ALL PRIVILEGES ON smart_learning_portfolio.*
  TO 'smart_learning_app'@'localhost';

FLUSH PRIVILEGES;

-- Application tables are also created by scripts/init_db.py for local development.
-- Keep this block in sync with the SQLAlchemy models when provisioning MySQL.
CREATE TABLE IF NOT EXISTS project_types (
  id INT PRIMARY KEY AUTO_INCREMENT,
  code VARCHAR(50) NOT NULL UNIQUE,
  name VARCHAR(100) NOT NULL,
  school_year INT NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT FALSE,
  created_at DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS requirement_templates (
  id INT PRIMARY KEY AUTO_INCREMENT,
  project_type_id INT NOT NULL,
  name VARCHAR(150) NOT NULL,
  version VARCHAR(30) NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT FALSE,
  created_at DATETIME NOT NULL,
  FOREIGN KEY (project_type_id) REFERENCES project_types(id)
);

CREATE TABLE IF NOT EXISTS requirement_items (
  id INT PRIMARY KEY AUTO_INCREMENT,
  template_id INT NOT NULL,
  title VARCHAR(150) NOT NULL,
  description TEXT NULL,
  stage VARCHAR(30) NOT NULL,
  is_required BOOLEAN NOT NULL DEFAULT TRUE,
  sort_order INT NOT NULL DEFAULT 0,
  FOREIGN KEY (template_id) REFERENCES requirement_templates(id)
);

CREATE TABLE IF NOT EXISTS project_groups (
  id INT PRIMARY KEY AUTO_INCREMENT,
  project_type_id INT NOT NULL,
  teacher_id INT NULL,
  name VARCHAR(100) NOT NULL,
  school_year INT NOT NULL,
  status VARCHAR(30) NOT NULL,
  created_at DATETIME NOT NULL,
  FOREIGN KEY (project_type_id) REFERENCES project_types(id),
  FOREIGN KEY (teacher_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS project_members (
  id INT PRIMARY KEY AUTO_INCREMENT,
  project_group_id INT NOT NULL,
  student_id INT NOT NULL,
  contribution TEXT NULL,
  status VARCHAR(30) NOT NULL,
  created_at DATETIME NOT NULL,
  FOREIGN KEY (project_group_id) REFERENCES project_groups(id),
  FOREIGN KEY (student_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS student_project_assignments (
  id INT PRIMARY KEY AUTO_INCREMENT,
  student_id INT NOT NULL,
  project_group_id INT NULL,
  template_id INT NOT NULL,
  status VARCHAR(30) NOT NULL,
  assigned_at DATETIME NOT NULL,
  FOREIGN KEY (student_id) REFERENCES users(id),
  FOREIGN KEY (project_group_id) REFERENCES project_groups(id),
  FOREIGN KEY (template_id) REFERENCES requirement_templates(id)
);

CREATE TABLE IF NOT EXISTS portfolio_submissions (
  id INT PRIMARY KEY AUTO_INCREMENT,
  portfolio_id INT NOT NULL,
  version_no INT NOT NULL,
  previous_submission_id INT NULL,
  status VARCHAR(30) NOT NULL,
  submitted_at DATETIME NULL,
  created_at DATETIME NOT NULL,
  FOREIGN KEY (portfolio_id) REFERENCES portfolios(id),
  FOREIGN KEY (previous_submission_id) REFERENCES portfolio_submissions(id)
);

CREATE TABLE IF NOT EXISTS portfolio_goal_snapshots (
  id INT PRIMARY KEY AUTO_INCREMENT,
  submission_id INT NOT NULL,
  requirement_item_id INT NULL,
  title VARCHAR(150) NOT NULL,
  description TEXT NULL,
  created_at DATETIME NOT NULL,
  FOREIGN KEY (submission_id) REFERENCES portfolio_submissions(id),
  FOREIGN KEY (requirement_item_id) REFERENCES requirement_items(id)
);

CREATE TABLE IF NOT EXISTS submission_evidence (
  id INT PRIMARY KEY AUTO_INCREMENT,
  submission_id INT NOT NULL,
  evidence_id INT NOT NULL,
  FOREIGN KEY (submission_id) REFERENCES portfolio_submissions(id),
  FOREIGN KEY (evidence_id) REFERENCES portfolio_evidence(id)
);

CREATE TABLE IF NOT EXISTS submission_assignments (
  id INT PRIMARY KEY AUTO_INCREMENT,
  submission_id INT NOT NULL,
  teacher_id INT NOT NULL,
  assigned_at DATETIME NOT NULL,
  FOREIGN KEY (submission_id) REFERENCES portfolio_submissions(id),
  FOREIGN KEY (teacher_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS project_review_results (
  id INT PRIMARY KEY AUTO_INCREMENT,
  submission_id INT NOT NULL,
  recorded_by_id INT NOT NULL,
  decision VARCHAR(30) NOT NULL,
  comment TEXT NULL,
  created_at DATETIME NOT NULL,
  FOREIGN KEY (submission_id) REFERENCES portfolio_submissions(id),
  FOREIGN KEY (recorded_by_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS project_revision_records (
  id INT PRIMARY KEY AUTO_INCREMENT,
  review_result_id INT NULL,
  submission_id INT NOT NULL,
  issue TEXT NOT NULL,
  resolution TEXT NULL,
  status VARCHAR(30) NOT NULL,
  created_at DATETIME NOT NULL,
  FOREIGN KEY (review_result_id) REFERENCES project_review_results(id),
  FOREIGN KEY (submission_id) REFERENCES portfolio_submissions(id)
);
