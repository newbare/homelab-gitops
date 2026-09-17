terraform {
  backend "local" {
    path = "env/dev/terraform.tfstate"
  }
}
