class Phylax < Formula
  desc "Back up Claude Code context and folders to your own Google Drive, encrypted"
  homepage "https://github.com/agentnetes/phylax"
  url "https://github.com/agentnetes/phylax/releases/download/v1.0.1/phylax-1.0.1.tar.gz"
  sha256 "42894929b028c92b2f01d5f8b4947d58bb5e02dd876151e54031ffbe518fa541"
  license "FSL-1.1-ALv2"
  depends_on "python"
  depends_on "rclone"
  depends_on "age"
  depends_on "gum"

  def install
    libexec.install Dir["*"]
    (bin/"phylax").write <<~EOS
      #!/bin/sh
      exec "#{Formula["python"].opt_bin}/python3" "#{opt_libexec}/phylax.py" "$@"
    EOS
  end

  def caveats
    "Run `phylax setup` to connect Google Drive and create your encryption key."
  end

  test do
    assert_match "phylax", shell_output("#{bin}/phylax --help")
  end
end
