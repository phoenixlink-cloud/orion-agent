FROM alpine:3.19

RUN apk add --no-cache git curl jq

WORKDIR /repos

# Clone repos with OAuth integration patterns we can learn from
# Shallow clones to save space — we only need the code, not history
RUN git clone --depth 1 https://github.com/open-webui/open-webui.git && \
    git clone --depth 1 https://github.com/nextauthjs/next-auth.git && \
    git clone --depth 1 https://github.com/supabase/auth.git supabase-auth && \
    git clone --depth 1 https://github.com/ToolJet/ToolJet.git && \
    git clone --depth 1 https://github.com/calcom/cal.com.git

CMD ["sh"]
